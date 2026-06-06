from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .jobs import ROOT, store


app = FastAPI(title="Bili Transcript Studio")
static_dir = ROOT / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class CreateJobRequest(BaseModel):
    url: str = Field(min_length=5)
    model: str = "large-v3-turbo"
    language: str = "zh"
    device: str = "auto"
    compute_type: str = "auto"
    max_parts: int | None = Field(default=None, ge=1)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.post("/api/jobs")
def create_job(payload: CreateJobRequest) -> dict:
    job = store.create(
        url=payload.url,
        model=payload.model,
        language=payload.language,
        device=payload.device,
        compute_type=payload.compute_type,
        max_parts=payload.max_parts,
    )
    return job.public()


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return [job.public() for job in store.list()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.public()


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str) -> FileResponse:
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    path_text = job.result_files.get(kind)
    if not path_text:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path, filename=path.name)

