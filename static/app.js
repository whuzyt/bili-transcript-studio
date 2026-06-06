const form = document.querySelector("#jobForm");
const jobsEl = document.querySelector("#jobs");
const jobCountEl = document.querySelector("#jobCount");
const refreshBtn = document.querySelector("#refreshBtn");

let pollTimer = null;

function pct(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderJob(job) {
  const title = job.title || job.url;
  const statusClass = job.status === "done" ? "done" : job.status === "failed" ? "failed" : "";
  const actions =
    job.status === "done"
      ? `<div class="job-actions">
          <a href="/api/jobs/${job.id}/download/merged_markdown">下载合并稿</a>
          <a href="#" data-path="${escapeHtml(job.output_dir)}">输出目录：${escapeHtml(job.output_dir)}</a>
        </div>`
      : "";
  const error = job.error ? `<pre class="error">${escapeHtml(job.error)}</pre>` : "";
  return `<article class="job">
    <div class="job-title">
      <strong>${escapeHtml(title)}</strong>
      <span class="status ${statusClass}">${escapeHtml(job.status)}</span>
    </div>
    <div class="meta">${escapeHtml(job.message)} · ${job.completed_parts}/${job.parts.length || 0} · ${pct(job.progress)}</div>
    <div class="progress"><div class="bar" style="width: ${pct(job.progress)}"></div></div>
    <div class="meta">${escapeHtml(job.current_part || "")}</div>
    ${actions}
    ${error}
  </article>`;
}

async function loadJobs() {
  const res = await fetch("/api/jobs");
  const jobs = await res.json();
  jobsEl.innerHTML = jobs.length
    ? jobs
        .slice()
        .reverse()
        .map(renderJob)
        .join("")
    : `<div class="job"><span class="meta">暂无任务</span></div>`;
  jobCountEl.textContent = jobs.length;

  const active = jobs.some((job) => ["queued", "running"].includes(job.status));
  if (active && !pollTimer) {
    pollTimer = setInterval(loadJobs, 2500);
  }
  if (!active && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  submit.textContent = "已提交";
  const payload = {
    url: form.url.value.trim(),
    model: form.model.value,
    language: form.language.value,
    device: form.device.value,
    compute_type: "auto",
    max_parts: form.maxParts.value ? Number(form.maxParts.value) : null,
  };
  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    await loadJobs();
  } finally {
    submit.disabled = false;
    submit.textContent = "开始转写";
  }
});

refreshBtn.addEventListener("click", loadJobs);
loadJobs();

