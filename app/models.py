from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]


@dataclass
class VideoPart:
    index: int
    title: str
    url: str
    duration: float | None = None
    video_id: str | None = None


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class Job:
    id: str
    url: str
    model: str
    language: str
    device: str
    compute_type: str
    max_parts: int | None
    status: JobStatus = "queued"
    progress: float = 0.0
    message: str = "等待开始"
    title: str | None = None
    output_dir: Path | None = None
    parts: list[VideoPart] = field(default_factory=list)
    completed_parts: int = 0
    current_part: str | None = None
    error: str | None = None
    result_files: dict[str, str] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "model": self.model,
            "language": self.language,
            "device": self.device,
            "compute_type": self.compute_type,
            "max_parts": self.max_parts,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "title": self.title,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "parts": [part.__dict__ for part in self.parts],
            "completed_parts": self.completed_parts,
            "current_part": self.current_part,
            "error": self.error,
            "result_files": self.result_files,
        }

