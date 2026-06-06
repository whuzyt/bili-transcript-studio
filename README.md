# Bili Transcript Studio

本地使用的 B 站视频转逐字稿工具。输入 B 站视频、合集或分 P 链接后，工具会解析分 P，下载音频，并使用本地开源 Whisper 模型生成逐字稿。

## 技术路线

- 后端：FastAPI
- 前端：原生 HTML/CSS/JavaScript
- 下载/解析：yt-dlp
- 转写优先级：
  1. Apple Silicon 上优先使用 `mlx-whisper` + `mlx-community/whisper-large-v3-turbo`
  2. 其他环境使用 `faster-whisper`，推荐模型 `large-v3-turbo`
  3. 本机已有的 `whisper` CLI 兜底
- 音频处理：ffmpeg

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
```

国内网络或已开启本机代理时，推荐使用：

```bash
mkdir -p .cache/pip
PIP_CACHE_DIR=.cache/pip .venv/bin/python -m pip install -r requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --trusted-host pypi.tuna.tsinghua.edu.cn \
  --retries 10 --timeout 60
```

如果使用 Hugging Face 模型下载镜像，可以复制 `.env.example` 为 `.env` 后按需修改。

如果只想先使用本机已有的 `whisper` 命令，可以不安装 `faster-whisper`，但建议安装依赖以获得更快的本地推理。Apple Silicon 机器建议安装 `mlx-whisper`，速度会明显更好。

## 启动

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

或：

```bash
bash scripts/run_app.sh
```

打开：

```text
http://127.0.0.1:8787
```

## 输出位置

所有任务输出在：

```text
data/jobs/<job_id>/
```

常用结果：

- `all_transcripts.md`：所有分 P 合并稿
- `transcripts/*.txt`：每个分 P 的纯文本
- `transcripts/*.srt`：带时间戳字幕
- `transcripts/*.json`：结构化分段结果

## 命令行跑指定链接

也可以不打开前端，直接使用：

```bash
.venv/bin/python -m app.cli "https://www.bilibili.com/video/BV18V411m76n" --model large-v3-turbo
```

本目录已内置这门课的全量任务脚本：

```bash
bash scripts/run_course.sh
```
