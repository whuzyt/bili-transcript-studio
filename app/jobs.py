from __future__ import annotations

import threading
import traceback
import uuid
import os
from pathlib import Path

from dotenv import load_dotenv

from .models import Job
from .pipeline import (
    download_subtitles,
    download_audio,
    ensure_tools,
    probe_bilibili,
    segments_from_subtitle,
    transcribe_audio,
    write_merged_markdown,
    write_transcript_files,
)


ROOT = Path(os.environ.get("BILI_TRANSCRIPT_ROOT", Path(__file__).resolve().parent.parent))
load_dotenv(ROOT / ".env")
DATA_DIR = ROOT / "data" / "jobs"


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(
        self,
        url: str,
        model: str = "large-v3-turbo",
        language: str = "zh",
        device: str = "auto",
        compute_type: str = "auto",
        max_parts: int | None = None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            url=url,
            model=model,
            language=language,
            device=device,
            compute_type=compute_type,
            max_parts=max_parts,
        )
        job.output_dir = DATA_DIR / job.id
        with self._lock:
            self._jobs[job.id] = job
        thread = threading.Thread(target=self._run, args=(job.id,), daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def _update(self, job_id: str, **changes: object) -> Job:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            return job

    def _run(self, job_id: str) -> None:
        job = self._update(job_id, status="running", message="检查本地工具", progress=0.01)
        try:
            ensure_tools()
            assert job.output_dir is not None
            audio_dir = job.output_dir / "audio"
            subtitle_dir = job.output_dir / "subtitles"
            transcript_dir = job.output_dir / "transcripts"
            job.output_dir.mkdir(parents=True, exist_ok=True)

            self._update(job_id, message="解析 B 站分 P", progress=0.03)
            title, parts = probe_bilibili(job.url, job.max_parts)
            self._update(job_id, title=title, parts=parts, message=f"解析到 {len(parts)} 个分 P", progress=0.08)

            total = max(len(parts), 1)
            completed_parts = []
            for offset, part in enumerate(parts):
                base = 0.08 + (offset / total) * 0.88
                self._update(
                    job_id,
                    current_part=part.title,
                    message=f"检查字幕 P{part.index:02d}",
                    progress=base,
                )
                subtitle_path = download_subtitles(part, subtitle_dir)
                if subtitle_path:
                    self._update(
                        job_id,
                        message=f"提取字幕 P{part.index:02d}",
                        progress=base + 0.04,
                    )
                    segments = segments_from_subtitle(subtitle_path)
                    source = "subtitle"
                if not subtitle_path or not segments:
                    self._update(
                        job_id,
                        message=f"下载音频 P{part.index:02d}",
                        progress=base + 0.02,
                    )
                    audio_path = download_audio(part, audio_dir)

                    self._update(
                        job_id,
                        message=f"本地模型转写 P{part.index:02d}",
                        progress=base + 0.05,
                    )
                    segments = transcribe_audio(
                        audio_path,
                        model=job.model,
                        language=job.language,
                        device=job.device,
                        compute_type=job.compute_type,
                    )
                    source = "asr"
                write_transcript_files(part, segments, transcript_dir, source=source)
                completed_parts.append(part)
                self._update(
                    job_id,
                    completed_parts=len(completed_parts),
                    message=f"完成 P{part.index:02d}",
                    progress=0.08 + ((offset + 1) / total) * 0.88,
                )

            merged = job.output_dir / "all_transcripts.md"
            write_merged_markdown(title, parts, transcript_dir, merged)
            self._update(
                job_id,
                status="done",
                progress=1.0,
                message="全部完成",
                current_part=None,
                result_files={
                    "merged_markdown": str(merged),
                    "transcripts_dir": str(transcript_dir),
                    "job_dir": str(job.output_dir),
                },
            )
        except Exception as exc:
            error = f"{exc}\n\n{traceback.format_exc()}"
            self._update(job_id, status="failed", message="任务失败", error=error)


store = JobStore()
