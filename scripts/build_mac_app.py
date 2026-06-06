from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "B站逐字稿"
APP_BUNDLE = ROOT / "dist" / f"{APP_NAME}.app"
CONTENTS = APP_BUNDLE / "Contents"
MACOS = CONTENTS / "MacOS"
RESOURCES = CONTENTS / "Resources"
BUNDLE_PROJECT = RESOURCES / "project"
BUNDLE_SITE_PACKAGES = RESOURCES / "python" / "site-packages"
ICONSET = ROOT / "build" / "BiliTranscript.iconset"
ICON_PNG = ROOT / "build" / "BiliTranscript_1024.png"
ICON_ICNS = RESOURCES / "BiliTranscript.icns"


def make_icon() -> None:
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True, exist_ok=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)

    if True:
        from PIL import Image, ImageDraw

        size = 1024
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle((72, 72, 952, 952), radius=220, fill=(32, 98, 77, 255))
        draw.rounded_rectangle((160, 142, 864, 882), radius=72, fill=(248, 250, 246, 255))
        draw.rounded_rectangle((208, 218, 816, 302), radius=28, fill=(223, 235, 226, 255))

        for y, w in [(390, 500), (470, 560), (550, 450), (630, 530)]:
            draw.rounded_rectangle((244, y, 244 + w, y + 28), radius=14, fill=(55, 76, 65, 255))

        draw.polygon([(642, 346), (642, 578), (820, 462)], fill=(234, 127, 54, 255))

        draw.rounded_rectangle((244, 704, 500, 746), radius=21, fill=(32, 98, 77, 255))
        draw.rounded_rectangle((244, 786, 650, 828), radius=21, fill=(32, 98, 77, 255))
        draw.rounded_rectangle((608, 686, 686, 858), radius=32, fill=(32, 98, 77, 255))

        ICON_PNG.parent.mkdir(parents=True, exist_ok=True)
        img.save(ICON_PNG)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for target_size, name in sizes:
        subprocess.run(
            ["sips", "-z", str(target_size), str(target_size), str(ICON_PNG), "--out", str(ICONSET / name)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    try:
        subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICON_ICNS)], check=True)
    except subprocess.CalledProcessError:
        tiff_path = ROOT / "build" / "BiliTranscript_1024.tiff"
        subprocess.run(
            ["sips", "-s", "format", "tiff", str(ICON_PNG), "--out", str(tiff_path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["tiff2icns", str(tiff_path), str(ICON_ICNS)], check=True)


def write_info_plist() -> None:
    info = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": "BiliTranscriptLauncher",
        "CFBundleIconFile": "BiliTranscript",
        "CFBundleIdentifier": "local.bili-transcript.studio",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0",
        "LSArchitecturePriority": ["arm64", "x86_64"],
        "NSDocumentsFolderUsageDescription": "B站逐字稿需要访问项目目录中的本地模型环境、任务数据和生成的逐字稿文件。",
        "NSDownloadsFolderUsageDescription": "B站逐字稿可能需要读取或打开下载目录中的视频和音频文件。",
        "NSHighResolutionCapable": True,
    }
    with (CONTENTS / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)


def write_launcher() -> None:
    launcher = MACOS / "BiliTranscriptLauncher"
    python_executable = ROOT / ".venv" / "bin" / "python"
    if python_executable.exists():
        resolved_python = python_executable.resolve()
    else:
        resolved_python = Path("/usr/bin/python3")
    script = f"""#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_ROOT="$APP_ROOT/Resources/project"
APP_DATA="$HOME/Library/Application Support/{APP_NAME}"
LOG_DIR="$APP_DATA/logs"
mkdir -p "$LOG_DIR"
mkdir -p "$APP_DATA"
cd "$PROJECT_ROOT"

if [ ! -f "$APP_DATA/.env" ] && [ -f "$PROJECT_ROOT/.env" ]; then
  cp "$PROJECT_ROOT/.env" "$APP_DATA/.env"
fi

export PYTHONUNBUFFERED=1
export BILI_TRANSCRIPT_ROOT="$APP_DATA"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONPATH="$PROJECT_ROOT:$APP_ROOT/Resources/python/site-packages"
exec /usr/bin/arch -arm64 "{resolved_python}" -m app.gui >> "$LOG_DIR/gui.log" 2>&1
"""
    launcher.write_text(script, encoding="utf-8")
    launcher.chmod(0o755)


def copy_runtime() -> None:
    if BUNDLE_PROJECT.exists():
        shutil.rmtree(BUNDLE_PROJECT)
    if BUNDLE_SITE_PACKAGES.exists():
        shutil.rmtree(BUNDLE_SITE_PACKAGES)

    BUNDLE_PROJECT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "app", BUNDLE_PROJECT / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "static", BUNDLE_PROJECT / "static", ignore=shutil.ignore_patterns(".DS_Store"))
    for name in (".env", ".env.example", "requirements.txt", "README.md"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, BUNDLE_PROJECT / name)

    source_site = ROOT / ".venv" / "lib" / "python3.11" / "site-packages"
    if not source_site.exists():
        raise FileNotFoundError(f"未找到依赖目录: {source_site}")
    shutil.copytree(
        source_site,
        BUNDLE_SITE_PACKAGES,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def build_app() -> None:
    if APP_BUNDLE.exists():
        shutil.rmtree(APP_BUNDLE)
    MACOS.mkdir(parents=True, exist_ok=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)
    make_icon()
    copy_runtime()
    write_info_plist()
    write_launcher()
    subprocess.run(["xattr", "-cr", str(APP_BUNDLE)], check=False)
    print(APP_BUNDLE)


if __name__ == "__main__":
    build_app()
