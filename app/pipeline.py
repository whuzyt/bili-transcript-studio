from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from pathlib import Path

from .models import TranscriptSegment, VideoPart
from .simplify import simplify_segments, to_simplified


ROOT = Path(os.environ.get("BILI_TRANSCRIPT_ROOT", Path(__file__).resolve().parent.parent))


class PipelineError(RuntimeError):
    pass


def ensure_tools() -> None:
    missing = [tool for tool in ("ffmpeg",) if shutil.which(tool) is None]
    if missing:
        raise PipelineError(f"缺少命令：{', '.join(missing)}")


def run_command(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=cwd or ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise PipelineError(detail or f"命令失败：{' '.join(args)}")
    return proc


def probe_bilibili(url: str, max_parts: int | None = None) -> tuple[str, list[VideoPart]]:
    api_result = probe_bilibili_pages_api(url, max_parts)
    if api_result:
        return api_result

    args = ytdlp_args("--flat-playlist", "--dump-single-json", "--skip-download", url)
    info = json.loads(run_command(args).stdout)
    title = info.get("title") or info.get("playlist_title") or "Bilibili video"
    entries = info.get("entries") or []

    if not entries:
        return title, [VideoPart(index=1, title=title, url=url, video_id=info.get("id"))]

    parts: list[VideoPart] = []
    for idx, entry in enumerate(entries, start=1):
        if max_parts and idx > max_parts:
            break
        part_url = entry.get("url") or entry.get("webpage_url") or f"{url.split('?')[0]}?p={idx}"
        if part_url.startswith("BV"):
            part_url = f"https://www.bilibili.com/video/{part_url}?p={idx}"
        elif "bilibili.com" not in part_url:
            part_url = f"{url.split('?')[0]}?p={idx}"
        parts.append(
            VideoPart(
                index=idx,
                title=entry.get("title") or f"P{idx:02d}",
                url=part_url,
                duration=entry.get("duration"),
                video_id=entry.get("id"),
            )
        )
    return title, parts


def probe_bilibili_pages_api(url: str, max_parts: int | None = None) -> tuple[str, list[VideoPart]] | None:
    bvid = extract_bvid(url)
    if not bvid:
        return None
    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    request = Request(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": f"https://www.bilibili.com/video/{bvid}",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if payload.get("code") != 0:
        return None

    data = payload.get("data") or {}
    title = data.get("title") or "Bilibili video"
    pages = data.get("pages") or []
    if not pages:
        return title, [VideoPart(index=1, title=title, url=f"https://www.bilibili.com/video/{bvid}", video_id=bvid)]

    parts = []
    for page in pages[: max_parts or None]:
        index = int(page.get("page") or len(parts) + 1)
        part_title = page.get("part") or f"P{index:02d}"
        parts.append(
            VideoPart(
                index=index,
                title=part_title,
                url=f"https://www.bilibili.com/video/{bvid}?p={index}",
                duration=page.get("duration"),
                video_id=str(page.get("cid")) if page.get("cid") else bvid,
            )
        )
    return title, parts


def extract_bvid(url: str) -> str | None:
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    match = re.search(r"(BV[0-9A-Za-z]+)", parsed.path)
    return match.group(1) if match else None


def safe_name(text: str, limit: int = 90) -> str:
    keep = []
    for char in text.strip():
        if char.isalnum() or char in " -_().[]【】":
            keep.append(char)
        else:
            keep.append("_")
    name = "".join(keep).strip(" ._")
    return (name[:limit] or "untitled").strip()


def download_audio(part: VideoPart, audio_dir: Path) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    stem = f"p{part.index:02d}_{safe_name(part.title, 70)}"
    output = audio_dir / f"{stem}.%(ext)s"
    args = ytdlp_args(
        "--no-playlist",
        "-f",
        "ba/bestaudio",
        "-x",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "-o",
        str(output),
        part.url,
    )
    run_command(args)
    wav = audio_dir / f"{stem}.wav"
    if not wav.exists():
        matches = sorted(audio_dir.glob(f"{stem}.*"))
        if not matches:
            raise PipelineError(f"未找到下载后的音频：{stem}")
        return matches[-1]
    return wav


def download_subtitles(part: VideoPart, subtitle_dir: Path) -> Path | None:
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    stem = f"p{part.index:02d}_{safe_name(part.title, 70)}"
    output = subtitle_dir / f"{stem}.%(ext)s"
    args = ytdlp_args(
        "--no-playlist",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "zh-Hans,zh-CN,zh,zh-Hant,zh-TW,all",
        "--sub-format",
        "json3/vtt/srt/best",
        "-o",
        str(output),
        part.url,
    )
    try:
        run_command(args)
    except PipelineError:
        return None

    candidates = []
    for path in subtitle_dir.glob(f"{stem}*"):
        if path.suffix.lower() in {".json3", ".vtt", ".srt"}:
            candidates.append(path)
    return sorted(candidates, key=subtitle_priority)[0] if candidates else None


def subtitle_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if ".zh-hans." in name or ".zh-cn." in name:
        lang_rank = 0
    elif ".zh." in name:
        lang_rank = 1
    elif ".zh-hant." in name or ".zh-tw." in name:
        lang_rank = 2
    else:
        lang_rank = 3
    ext_rank = {".json3": 0, ".srt": 1, ".vtt": 2}.get(path.suffix.lower(), 9)
    return (lang_rank, ext_rank, name)


def segments_from_subtitle(path: Path) -> list[TranscriptSegment]:
    suffix = path.suffix.lower()
    if suffix == ".json3":
        return segments_from_json3(path)
    if suffix == ".srt":
        return segments_from_srt(path)
    if suffix == ".vtt":
        return segments_from_vtt(path)
    return []


def segments_from_json3(path: Path) -> list[TranscriptSegment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = []
    for event in data.get("events", []):
        start_ms = event.get("tStartMs")
        duration_ms = event.get("dDurationMs") or 0
        segs = event.get("segs") or []
        text = "".join(str(seg.get("utf8", "")) for seg in segs).strip()
        if start_ms is None or not text:
            continue
        start = float(start_ms) / 1000
        end = float(start_ms + duration_ms) / 1000 if duration_ms else start
        segments.append(TranscriptSegment(start=start, end=end, text=clean_subtitle_text(text)))
    return merge_subtitle_segments(segments)


def segments_from_srt(path: Path) -> list[TranscriptSegment]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timing_line = next((line for line in lines if "-->" in line), "")
        if not timing_line:
            continue
        timing_index = lines.index(timing_line)
        start_text, end_text = [part.strip() for part in timing_line.split("-->", 1)]
        body = " ".join(lines[timing_index + 1 :]).strip()
        if body:
            segments.append(
                TranscriptSegment(
                    start=parse_subtitle_time(start_text),
                    end=parse_subtitle_time(end_text),
                    text=clean_subtitle_text(body),
                )
            )
    return merge_subtitle_segments(segments)


def segments_from_vtt(path: Path) -> list[TranscriptSegment]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or lines[0].upper().startswith("WEBVTT"):
            continue
        timing_line = next((line for line in lines if "-->" in line), "")
        if not timing_line:
            continue
        timing_index = lines.index(timing_line)
        start_text, end_text = [part.strip().split()[0] for part in timing_line.split("-->", 1)]
        body = " ".join(lines[timing_index + 1 :]).strip()
        if body:
            segments.append(
                TranscriptSegment(
                    start=parse_subtitle_time(start_text),
                    end=parse_subtitle_time(end_text),
                    text=clean_subtitle_text(body),
                )
            )
    return merge_subtitle_segments(segments)


def parse_subtitle_time(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = "0", parts[0], parts[1]
    else:
        return 0.0
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_subtitle_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{\\.*?\}", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return to_simplified(re.sub(r"\s+", " ", text).strip())


def merge_subtitle_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    cleaned = []
    previous_text = None
    for seg in segments:
        text = clean_subtitle_text(seg.text)
        if not text or text == previous_text:
            continue
        cleaned.append(TranscriptSegment(start=seg.start, end=seg.end, text=text))
        previous_text = text
    return simplify_segments(cleaned)


def format_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_transcript_files(
    part: VideoPart,
    segments: list[TranscriptSegment],
    transcript_dir: Path,
    source: str = "asr",
) -> dict[str, Path]:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    stem = f"p{part.index:02d}_{safe_name(part.title, 70)}"
    txt_path = transcript_dir / f"{stem}.txt"
    srt_path = transcript_dir / f"{stem}.srt"
    json_path = transcript_dir / f"{stem}.json"

    segments = simplify_segments(segments)
    text = "\n".join(to_simplified(seg.text.strip()) for seg in segments if seg.text.strip())
    txt_path.write_text(text + "\n", encoding="utf-8")

    srt_blocks = []
    for idx, seg in enumerate(segments, start=1):
        srt_blocks.append(
            f"{idx}\n{format_time(seg.start)} --> {format_time(seg.end)}\n{to_simplified(seg.text.strip())}\n"
        )
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

    json_path.write_text(
        json.dumps(
            {
                "index": part.index,
                "title": to_simplified(part.title),
                "url": part.url,
                "source": source,
                "segments": [
                    {
                        "start": seg.start,
                        "end": seg.end,
                        "text": to_simplified(seg.text),
                    }
                    for seg in segments
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"txt": txt_path, "srt": srt_path, "json": json_path}


def transcribe_audio(
    audio_path: Path,
    model: str,
    language: str,
    device: str,
    compute_type: str,
) -> list[TranscriptSegment]:
    mlx_segments = transcribe_with_mlx(audio_path, model, language)
    if mlx_segments is not None:
        return mlx_segments

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return transcribe_with_cli(audio_path, model, language)

    whisper = WhisperModel(model, device=device, compute_type=compute_type)
    segments, _ = whisper.transcribe(
        str(audio_path),
        language=language or None,
        vad_filter=True,
        beam_size=5,
    )
    return simplify_segments([
        TranscriptSegment(start=float(seg.start), end=float(seg.end), text=seg.text.strip())
        for seg in segments
        if seg.text.strip()
    ])


def transcribe_with_mlx(audio_path: Path, model: str, language: str) -> list[TranscriptSegment] | None:
    repo = mlx_repo_for_model(model)
    if repo is None:
        return None
    try:
        import mlx_whisper
    except Exception:
        return None

    try:
        result = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=repo,
            language=language or None,
            verbose=False,
            condition_on_previous_text=False,
        )
    except Exception:
        return None

    return simplify_segments([
        TranscriptSegment(
            start=float(seg.get("start", 0)),
            end=float(seg.get("end", 0)),
            text=str(seg.get("text", "")).strip(),
        )
        for seg in result.get("segments", [])
        if str(seg.get("text", "")).strip()
    ])


def mlx_repo_for_model(model: str) -> str | None:
    mapping = {
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "large-v3": "mlx-community/whisper-large-v3",
        "medium": "mlx-community/whisper-medium",
        "small": "mlx-community/whisper-small",
    }
    return mapping.get(model)


def transcribe_with_cli(audio_path: Path, model: str, language: str) -> list[TranscriptSegment]:
    if shutil.which("whisper") is None:
        raise PipelineError("未安装 faster-whisper，且找不到 whisper CLI")

    out_dir = audio_path.parent / "_whisper_cli"
    out_dir.mkdir(exist_ok=True)
    args = [
        "whisper",
        str(audio_path),
        "--model",
        model.replace("-turbo", ""),
        "--language",
        language or "zh",
        "--output_format",
        "json",
        "--output_dir",
        str(out_dir),
    ]
    run_command(args)
    json_path = out_dir / f"{audio_path.stem}.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return simplify_segments([
        TranscriptSegment(start=float(seg["start"]), end=float(seg["end"]), text=seg["text"].strip())
        for seg in data.get("segments", [])
        if seg.get("text", "").strip()
    ])


def ytdlp_args(*args: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "yt_dlp",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "--add-header",
        "Referer:https://www.bilibili.com/",
        "--no-warnings",
        *args,
    ]


def write_merged_markdown(title: str, parts: list[VideoPart], transcript_dir: Path, output_path: Path) -> None:
    chunks = [f"# {to_simplified(title)}", ""]
    for part in parts:
        stem_prefix = f"p{part.index:02d}_"
        txt_files = sorted(transcript_dir.glob(f"{stem_prefix}*.txt"))
        chunks.extend([f"## P{part.index:02d} {to_simplified(part.title)}", ""])
        if txt_files:
            chunks.append(to_simplified(txt_files[0].read_text(encoding="utf-8").strip()))
        else:
            chunks.append("_未生成_")
        chunks.append("")
    output_path.write_text("\n".join(chunks).strip() + "\n", encoding="utf-8")
