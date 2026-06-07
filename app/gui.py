from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .jobs import ROOT, store


MODELS = ("large-v3-turbo", "large-v3", "medium", "small")
BG_MAIN = "#FFFFFF"
BG_CARD = "#FFFFFF"
BG_INPUT = "#FFFFFF"
BG_CONSOLE = "#FFFFFF"
BG_HOVER = "#F7F7F8"
BORDER = "#E5E5E5"
BORDER_FOCUS = "#D1D5DB"
TEXT = "#202123"
MUTED = "#8E8EA0"
ACCENT = "#10A37F"
ACCENT_2 = "#19C37D"
SUCCESS = "#16803C"
WARNING = "#B45309"
RUNNING = "#0A7C66"
ERROR = "#D92D20"


def app_font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return ("SF Pro Text", size, weight)


def display_font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return ("SF Pro Display", size, weight)


def mono_font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return ("SF Mono", size, weight)


class RoundedFrame(tk.Canvas):
    def __init__(
        self,
        parent,
        radius: int = 12,
        fill: str = BG_INPUT,
        outline: str = BORDER,
        outer_bg: str = BG_CARD,
        line_width: int = 1,
        **kwargs,
    ):
        super().__init__(parent, bg=outer_bg, highlightthickness=0, bd=0, **kwargs)
        self.radius = radius
        self.fill = fill
        self.outline = outline
        self.line_width = line_width
        self.inner = tk.Frame(self, bg=fill)
        self._window = self.create_window(2, 2, anchor="nw", window=self.inner)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event) -> None:
        self.delete("shape")
        width = max(event.width - 2, 1)
        height = max(event.height - 2, 1)
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
        self.create_polygon(points, smooth=True, fill=self.fill, outline=self.outline, width=self.line_width, tags="shape")
        self.tag_lower("shape")
        inset = max(self.line_width + 1, 2)
        self.coords(self._window, inset, inset)
        self.itemconfigure(self._window, width=max(width - inset * 2 + 1, 1), height=max(height - inset * 2 + 1, 1))

    def set_outline(self, color: str) -> None:
        self.outline = color
        event = type("ConfigureEvent", (), {"width": self.winfo_width(), "height": self.winfo_height()})()
        self._redraw(event)


class ActionCard(tk.Canvas):
    def __init__(self, parent, icon: str, label: str, command) -> None:
        super().__init__(
            parent,
            width=128,
            height=96,
            bg=BG_CARD,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.icon = icon
        self.label = label
        self.command = command
        self.state = tk.DISABLED
        self.hover = False
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        state = kwargs.pop("state", None)
        result = super().configure(cnf, **kwargs)
        if state is not None:
            self.state = state
            self.configure(cursor="hand2" if state == tk.NORMAL else "arrow")
            self._draw()
        return result

    def _draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width() - 2, 1)
        height = max(self.winfo_height() - 2, 1)
        fill = BG_HOVER if self.hover and self.state == tk.NORMAL else BG_INPUT
        outline = BORDER_FOCUS if self.hover and self.state == tk.NORMAL else BORDER
        text_color = TEXT if self.state == tk.NORMAL else "#C7C7C7"
        icon_color = "#6B7280" if self.state == tk.NORMAL else "#D1D5DB"
        self._rounded_rect(1, 1, width, height, 10, fill=fill, outline=outline)
        self.create_text(width / 2, 34, text=self.icon, fill=icon_color, font=display_font(24))
        self.create_text(width / 2, 68, text=self.label, fill=text_color, font=app_font(12, "bold"))

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs) -> None:
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        self.create_polygon(points, smooth=True, **kwargs)

    def _on_enter(self, _event) -> None:
        self.hover = True
        self._draw()

    def _on_leave(self, _event) -> None:
        self.hover = False
        self._draw()

    def _on_click(self, _event) -> None:
        if self.state == tk.NORMAL:
            self.command()


class TranscriptStudio(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("B站逐字稿")
        self.geometry("640x780")
        self.minsize(600, 700)

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
        self.configure(bg=BG_MAIN)

        outer_shell = tk.Frame(self, bg=BG_MAIN, padx=22, pady=22)
        outer_shell.pack(fill=tk.BOTH, expand=True)
        outer_shell.columnconfigure(0, weight=1)
        outer_shell.rowconfigure(0, weight=1)

        window = RoundedFrame(outer_shell, radius=14, fill=BG_CARD, outline=BORDER, outer_bg=BG_MAIN)
        window.grid(row=0, column=0, sticky="nsew")
        window.inner.columnconfigure(0, weight=1)
        window.inner.rowconfigure(0, weight=1)

        outer = tk.Frame(window.inner, bg=BG_CARD, padx=32, pady=30)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        brand = tk.Frame(outer, bg=BG_CARD)
        brand.grid(row=0, column=0, sticky="ew")
        tk.Label(
            brand,
            text="✨ B站视频转逐字稿",
            bg=BG_CARD,
            fg=TEXT,
            font=display_font(22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="优雅地利用本地 Whisper 模型，将多 P 或单视频快速重构为高质量文本文件。",
            bg=BG_CARD,
            fg=MUTED,
            font=app_font(13),
            wraplength=520,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(8, 0))

        input_shell = RoundedFrame(outer, radius=12, fill=BG_INPUT, outline=ACCENT, outer_bg=BG_CARD, line_width=1)
        input_shell.grid(row=1, column=0, sticky="ew", pady=(28, 26), ipady=2)
        form = input_shell.inner
        form.columnconfigure(1, weight=1)

        tk.Label(form, text="🔗", bg=BG_INPUT, fg=MUTED, font=display_font(18)).grid(row=0, column=0, sticky="nw", padx=(16, 10), pady=(16, 0))
        url_entry = tk.Entry(
            form,
            textvariable=self.url_var,
            bg=BG_INPUT,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            font=app_font(14),
        )
        url_entry.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(18, 34))
        url_entry.insert(0, "")
        url_entry.focus_set()
        url_entry.bind("<FocusIn>", lambda _event: input_shell.set_outline(ACCENT_2))
        url_entry.bind("<FocusOut>", lambda _event: input_shell.set_outline(ACCENT))

        divider = tk.Frame(form, bg=BORDER, height=1)
        divider.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16)

        config = tk.Frame(form, bg=BG_INPUT)
        config.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=14)
        config.columnconfigure(4, weight=1)

        tk.Label(config, text="模型", bg=BG_INPUT, fg=MUTED, font=app_font(12)).grid(row=0, column=0, sticky="w", padx=(0, 8))
        model_menu = tk.OptionMenu(config, self.model_var, *MODELS)
        model_menu.configure(
            bg=BG_CARD,
            fg=TEXT,
            activebackground=BG_HOVER,
            activeforeground=TEXT,
            highlightthickness=1,
            highlightbackground=BORDER,
            relief=tk.FLAT,
            bd=0,
            font=app_font(12),
            width=15,
        )
        model_menu["menu"].configure(bg=BG_CARD, fg=TEXT, activebackground=BG_HOVER, activeforeground=TEXT)
        model_menu.grid(row=0, column=1, sticky="w")

        tk.Label(config, text="分 P 上限", bg=BG_INPUT, fg=MUTED, font=app_font(12)).grid(row=0, column=2, sticky="w", padx=(14, 8))
        max_parts = tk.Entry(
            config,
            textvariable=self.max_parts_var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER_FOCUS,
            font=app_font(12),
            width=5,
            justify=tk.CENTER,
        )
        max_parts.grid(row=0, column=3, sticky="w")

        self.start_button = tk.Button(
            config,
            text="开始转写",
            command=self.start_job,
            bg="#FAFAFA",
            fg="#8E8EA0",
            activebackground="#F4F4F5",
            activeforeground="#6B7280",
            disabledforeground="#B9B9C3",
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER_FOCUS,
            padx=16,
            pady=8,
            cursor="hand2",
            font=app_font(13, "bold"),
        )
        self.start_button.grid(row=0, column=5, sticky="e")

        console = tk.Frame(outer, bg=BG_CARD)
        console.grid(row=2, column=0, sticky="nsew")
        console.columnconfigure(0, weight=1)
        console.rowconfigure(2, weight=1)

        tk.Label(
            console,
            text="CONSOLE OUTPUT",
            bg=BG_CARD,
            fg=MUTED,
            font=mono_font(12, "bold"),
        ).grid(row=0, column=0, sticky="w")

        progress_wrap = tk.Frame(console, bg="#F1F1F1", height=4)
        progress_wrap.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        progress_wrap.grid_propagate(False)
        self.progress_fill = tk.Frame(progress_wrap, bg=ACCENT, width=1)
        self.progress_fill.place(x=0, y=0, relheight=1, relwidth=0)

        log_shell = RoundedFrame(console, radius=8, fill=BG_CONSOLE, outline=BORDER, outer_bg=BG_CARD)
        log_shell.grid(row=2, column=0, sticky="nsew")
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
            bg=BG_CONSOLE,
            fg=TEXT,
            insertbackground=TEXT,
            padx=16,
            pady=14,
            font=mono_font(13),
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(log_frame, command=self.log.yview, bg=BG_CONSOLE, troughcolor=BG_CONSOLE, activebackground=BORDER)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.tag_configure("success", foreground=SUCCESS)
        self.log.tag_configure("warning", foreground=WARNING)
        self.log.tag_configure("running", foreground=RUNNING)
        self.log.tag_configure("error", foreground=ERROR)
        self.log.tag_configure("muted", foreground=MUTED)

        actions = tk.Frame(outer, bg=BG_CARD)
        actions.grid(row=3, column=0, sticky="ew", pady=(28, 0))
        for index in range(3):
            actions.columnconfigure(index, weight=1, uniform="actions")

        self.open_job_button = ActionCard(actions, "📂", "任务目录", lambda: self.open_result("job_dir"))
        self.open_transcripts_button = ActionCard(
            actions,
            "📝",
            "逐字稿目录",
            lambda: self.open_result("transcripts_dir"),
        )
        self.open_merged_button = ActionCard(
            actions,
            "📄",
            "合并稿",
            lambda: self.open_result("merged_markdown"),
        )
        self.open_job_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.open_transcripts_button.grid(row=0, column=1, sticky="ew", padx=8)
        self.open_merged_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    def _load_recent_hint(self) -> None:
        self.write_log("✓ 环境检查完毕，服务就绪", "success")
        self.write_log("✓ 会优先抓取 B 站原生字幕数据", "success")
        self.write_log("⚡ 无字幕时将使用本地 Whisper 解析音频", "running")
        self.write_log(f"[Path] {ROOT}", "muted")

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
        self._update_progress_bar(0)
        self.log.delete("1.0", tk.END)
        self.write_log("⚡ 任务已创建，开始调用本地转写管线。", "running")
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
        self.write_log(f"[Job] {job.id}", "muted")
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
        self._update_progress_bar(percent)
        part = f"｜当前：{job.current_part}" if job.current_part else ""
        self.status_var.set(f"{percent}%｜{job.message}{part}")

        self.write_log_once(
            f"{job.status}:{percent}:{job.message}:{job.current_part or ''}",
            f"⚡ {self.status_var.get()}",
            "running",
        )

        if job.status == "done":
            self.current_result_files = job.result_files
            self.write_log("✓ 全部完成。可以打开任务目录或合并稿查看结果。", "success")
            self.set_result_buttons(tk.NORMAL)
            self.start_button.configure(state=tk.NORMAL)
            return

        if job.status == "failed":
            self.write_log("✕ 任务失败。错误信息如下：", "error")
            self.write_log(job.error or "未知错误", "error")
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
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def write_log(self, text: str, tag: str | None = None) -> None:
        start = tk.END
        self.log.insert(tk.END, text.rstrip() + "\n")
        if tag:
            self.log.tag_add(tag, start, tk.END)
        self.log.see(tk.END)

    def write_log_once(self, key: str, text: str, tag: str | None = None) -> None:
        previous = getattr(self, "_last_log_key", None)
        if previous == key:
            return
        self._last_log_key = key
        self.write_log(text, tag)

    def _update_progress_bar(self, percent: float) -> None:
        self.progress_fill.place_configure(relwidth=max(0, min(percent, 100)) / 100)


def main() -> None:
    app = TranscriptStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
