from __future__ import annotations

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .jobs import ROOT, store


MODELS = ("large-v3-turbo", "large-v3", "medium", "small")
BG = "#ffffff"
TEXT = "#202123"
MUTED = "#6e6e73"
LINE = "#e7e7e7"
FIELD = "#fbfbfb"
ACCENT = "#10a37f"


def app_font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return ("SF Pro Text", size, weight)


class RoundedFrame(tk.Canvas):
    def __init__(self, parent, radius: int = 14, fill: str = FIELD, outline: str = LINE, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, **kwargs)
        self.radius = radius
        self.fill = fill
        self.outline = outline
        self.inner = tk.Frame(self, bg=fill)
        self._window = self.create_window(1, 1, anchor="nw", window=self.inner)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event) -> None:
        self.delete("shape")
        width = max(event.width - 1, 1)
        height = max(event.height - 1, 1)
        r = min(self.radius, width // 2, height // 2)
        points = [
            1 + r, 1,
            width - r, 1,
            width, 1,
            width, 1 + r,
            width, height - r,
            width, height,
            width - r, height,
            1 + r, height,
            1, height,
            1, height - r,
            1, 1 + r,
            1, 1,
        ]
        self.create_polygon(points, smooth=True, fill=self.fill, outline=self.outline, width=1, tags="shape")
        self.tag_lower("shape")
        self.coords(self._window, 2, 2)
        self.itemconfigure(self._window, width=max(width - 3, 1), height=max(height - 3, 1))


class TranscriptStudio(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("B站逐字稿")
        self.geometry("820x620")
        self.minsize(760, 560)

        self.current_job_id: str | None = None
        self.current_result_files: dict[str, str] = {}

        self.url_var = tk.StringVar()
        self.model_var = tk.StringVar(value="large-v3-turbo")
        self.max_parts_var = tk.StringVar()
        self.status_var = tk.StringVar(value="等待任务")
        self.progress_var = tk.DoubleVar(value=0)

        self._build_ui()
        self._load_recent_hint()

    def _build_ui(self) -> None:
        self.configure(bg=BG)
        outer = ttk.Frame(self, padding=22)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        title = ttk.Label(outer, text="B站视频转逐字稿", style="Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            outer,
            text="输入视频链接，使用本地模型转写，结果会保存到任务目录。",
            style="Subtitle.TLabel",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 18))

        form = ttk.Frame(outer)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="B站链接").grid(row=0, column=0, sticky="w", padx=(0, 10))
        url_entry = ttk.Entry(form, textvariable=self.url_var)
        url_entry.grid(row=0, column=1, sticky="ew")
        url_entry.focus_set()

        options = ttk.Frame(form)
        options.grid(row=1, column=1, sticky="ew", pady=(12, 0))
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="模型").grid(row=0, column=0, sticky="w", padx=(0, 10))
        model_box = ttk.Combobox(options, textvariable=self.model_var, values=MODELS, state="readonly", width=18)
        model_box.grid(row=0, column=1, sticky="w")

        ttk.Label(options, text="分P上限").grid(row=0, column=2, sticky="w", padx=(28, 10))
        max_parts = ttk.Entry(options, textvariable=self.max_parts_var, width=10)
        max_parts.grid(row=0, column=3, sticky="w")

        self.start_button = ttk.Button(form, text="开始转写", command=self.start_job)
        self.start_button.grid(row=0, column=2, sticky="e", padx=(14, 0))

        progress_area = ttk.Frame(outer)
        progress_area.grid(row=3, column=0, sticky="ew", pady=(22, 14))
        progress_area.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_area, variable=self.progress_var, maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_area, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(8, 0))

        log_shell = RoundedFrame(outer, radius=16, fill=FIELD, outline=LINE)
        log_shell.grid(row=4, column=0, sticky="nsew")
        log_frame = log_shell.inner
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log = tk.Text(
            log_frame,
            height=14,
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            padx=16,
            pady=14,
            font=app_font(13),
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        actions = ttk.Frame(outer)
        actions.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        self.open_job_button = ttk.Button(actions, text="打开任务目录", command=lambda: self.open_result("job_dir"), state=tk.DISABLED)
        self.open_transcripts_button = ttk.Button(
            actions,
            text="打开逐字稿目录",
            command=lambda: self.open_result("transcripts_dir"),
            state=tk.DISABLED,
        )
        self.open_merged_button = ttk.Button(
            actions,
            text="打开合并稿",
            command=lambda: self.open_result("merged_markdown"),
            state=tk.DISABLED,
        )
        self.open_job_button.pack(side=tk.LEFT)
        self.open_transcripts_button.pack(side=tk.LEFT, padx=(10, 0))
        self.open_merged_button.pack(side=tk.LEFT, padx=(10, 0))

        self._configure_styles()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        else:
            style.theme_use("clam")
        style.configure(".", font=app_font(13), background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Title.TLabel", font=("SF Pro Display", 24, "bold"), foreground=TEXT, background=BG)
        style.configure("Subtitle.TLabel", font=app_font(13), foreground=MUTED, background=BG)
        style.configure("TLabel", font=app_font(13), foreground=TEXT, background=BG)
        style.configure("TButton", font=app_font(13), padding=(14, 8), foreground=TEXT)
        style.configure("TEntry", font=app_font(13), fieldbackground=FIELD, padding=7)
        style.configure("TCombobox", font=app_font(13), fieldbackground=FIELD, padding=6)
        style.configure("Horizontal.TProgressbar", troughcolor="#f2f2f2", background=ACCENT)

    def _load_recent_hint(self) -> None:
        self.write_log("准备就绪。可以粘贴 B 站视频链接开始转写。")
        self.write_log("会先尝试提取 B 站字幕；没有可用字幕时，再使用本地模型转写。")
        self.write_log(f"数据目录：{ROOT}")

    def start_job(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("缺少链接", "请先输入 B 站视频链接。")
            return

        max_parts_text = self.max_parts_var.get().strip()
        max_parts: int | None = None
        if max_parts_text:
            try:
                max_parts = int(max_parts_text)
                if max_parts <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("分P上限无效", "分P上限请输入正整数，或者留空表示全部。")
                return

        self.current_result_files = {}
        self.set_result_buttons(tk.DISABLED)
        self.progress_var.set(0)
        self.log.delete("1.0", tk.END)
        self.write_log("任务已创建，开始调用本地转写管线。")
        self.start_button.configure(state=tk.DISABLED)

        job = store.create(
            url=url,
            model=self.model_var.get(),
            language="zh",
            device="auto",
            compute_type="auto",
            max_parts=max_parts,
        )
        self.current_job_id = job.id
        self.write_log(f"任务 ID：{job.id}")
        self.after(700, self.poll_job)

    def poll_job(self) -> None:
        if not self.current_job_id:
            return
        job = store.get(self.current_job_id)
        if job is None:
            self.status_var.set("任务不存在")
            self.start_button.configure(state=tk.NORMAL)
            return

        percent = round(job.progress * 100)
        self.progress_var.set(percent)
        part = f"｜当前：{job.current_part}" if job.current_part else ""
        self.status_var.set(f"{percent}%｜{job.message}{part}")

        self.write_log_once(f"{job.status}:{percent}:{job.message}:{job.current_part or ''}", self.status_var.get())

        if job.status == "done":
            self.current_result_files = job.result_files
            self.write_log("全部完成。可以打开任务目录或合并稿查看结果。")
            self.set_result_buttons(tk.NORMAL)
            self.start_button.configure(state=tk.NORMAL)
            return

        if job.status == "failed":
            self.write_log("任务失败。错误信息如下：")
            self.write_log(job.error or "未知错误")
            self.start_button.configure(state=tk.NORMAL)
            messagebox.showerror("任务失败", job.error or "未知错误")
            return

        self.after(1200, self.poll_job)

    def set_result_buttons(self, state: str) -> None:
        self.open_job_button.configure(state=state)
        self.open_transcripts_button.configure(state=state)
        self.open_merged_button.configure(state=state)

    def open_result(self, kind: str) -> None:
        path_text = self.current_result_files.get(kind)
        if not path_text:
            messagebox.showinfo("暂无结果", "这个结果还没有生成。")
            return
        path = Path(path_text)
        if not path.exists():
            messagebox.showerror("文件不存在", f"找不到：{path}")
            return
        subprocess.run(["open", str(path)], check=False)

    def write_log(self, text: str) -> None:
        self.log.insert(tk.END, text.rstrip() + "\n")
        self.log.see(tk.END)

    def write_log_once(self, key: str, text: str) -> None:
        previous = getattr(self, "_last_log_key", None)
        if previous == key:
            return
        self._last_log_key = key
        self.write_log(text)


def main() -> None:
    app = TranscriptStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
