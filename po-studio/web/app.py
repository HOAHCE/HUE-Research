"""PO-Studio web backend (FastAPI).

Run:  uvicorn web.app:app --host 0.0.0.0 --port 8000
Env:
  ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY   server-side keys (optional if users bring their own)
  POSTUDIO_ACCESS_CODE   if set, required (header X-Access-Code) to create jobs with the server's keys
  POSTUDIO_JOBS_DIR      where jobs are stored (default ./jobs)
  POSTUDIO_MAX_JOBS      concurrent jobs (default 2)
  OPENALEX_MAILTO        contact e-mail for the OpenAlex polite pool
  POSTUDIO_BRIDGE_TOKEN  if set, every /api/* call must carry header X-Bridge-Token with this value
                         (use it when the service sits behind the hi.hue.vn bridge /api/paper/*)
  POSTUDIO_ENABLE_MOCK   "1" adds the offline "mock" model (fake LLM + fake references) for demos/tests only
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from postudio.inputs import build_raw_materials  # noqa: E402
from postudio.pipeline import JobConfig, Pipeline, list_templates  # noqa: E402

JOBS_DIR = os.path.abspath(os.environ.get("POSTUDIO_JOBS_DIR", "jobs"))
ACCESS_CODE = os.environ.get("POSTUDIO_ACCESS_CODE", "")
MAX_UPLOAD_MB = int(os.environ.get("POSTUDIO_MAX_UPLOAD_MB", "60"))
BRIDGE_TOKEN = os.environ.get("POSTUDIO_BRIDGE_TOKEN", "")
ENABLE_MOCK = os.environ.get("POSTUDIO_ENABLE_MOCK") == "1"
os.makedirs(JOBS_DIR, exist_ok=True)

app = FastAPI(title="PO-Studio", version="0.1.0")


@app.middleware("http")
async def bridge_guard(request: Request, call_next):
    """When POSTUDIO_BRIDGE_TOKEN is set, only the trusted web bridge may call the API."""
    if BRIDGE_TOKEN and request.url.path.startswith("/api/"):
        import hmac
        if not hmac.compare_digest(request.headers.get("x-bridge-token", ""), BRIDGE_TOKEN):
            return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"ok": True}
executor = ThreadPoolExecutor(max_workers=int(os.environ.get("POSTUDIO_MAX_JOBS", "2")))
running: dict[str, threading.Thread] = {}

STATIC = os.path.join(os.path.dirname(__file__), "static")
MODELS = {
    "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
    "gemini": ["gemini-3.1-pro-preview", "gemini-3-flash-preview"],
    "openai": ["gpt-5", "gpt-5-mini"],
}
if ENABLE_MOCK:
    MODELS["mock"] = ["mock"]


def _provider(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("mock"):
        if not ENABLE_MOCK:
            raise HTTPException(400, "mock model is disabled on this server")
        return "mock"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    raise HTTPException(400, "unknown model")
ALLOWED_DOWNLOADS = {"pdf": "final/paper.pdf", "tex": "final/paper.tex", "bib": "final/references.bib",
                     "zip": "submission_package.zip", "report": "report.md", "log": "pipeline.log",
                     "outline": "outline.json"}


def _job_dir(job_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise HTTPException(404, "job not found")
    d = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(d):
        raise HTTPException(404, "job not found")
    return d


async def _save_uploads(files: Optional[List[UploadFile]], dest: str, total: list) -> list:
    out = []
    os.makedirs(dest, exist_ok=True)
    for uf in files or []:
        if not uf or not uf.filename:
            continue
        name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(uf.filename))[:120]
        data = await uf.read()
        total[0] += len(data)
        if total[0] > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"uploads exceed {MAX_UPLOAD_MB} MB")
        p = os.path.join(dest, name)
        with open(p, "wb") as f:
            f.write(data)
        out.append(p)
    return out


@app.get("/", response_class=HTMLResponse)
def index():
    return open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()


@app.get("/api/config")
def config():
    server_keys = {p: bool(os.environ.get(k)) for p, k in
                   [("anthropic", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("openai", "OPENAI_API_KEY")]}
    if ENABLE_MOCK:
        server_keys["mock"] = True
    return {"templates": list_templates(), "models": MODELS, "server_keys": server_keys,
            "access_code_required": bool(ACCESS_CODE), "max_upload_mb": MAX_UPLOAD_MB}


@app.post("/api/jobs")
async def create_job(
    payload: str = Form(...),
    api_key: str = Form(""),
    data_files: Optional[List[UploadFile]] = File(None),
    result_files: Optional[List[UploadFile]] = File(None),
    figure_files: Optional[List[UploadFile]] = File(None),
    reference_files: Optional[List[UploadFile]] = File(None),
    note_files: Optional[List[UploadFile]] = File(None),
    x_access_code: str = Header(""),
):
    try:
        p = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, "payload must be JSON")
    form, opts = p.get("form", {}), p.get("options", {})
    writer = opts.get("writer_model", "claude-sonnet-5-5")
    provider = _provider(writer)
    reviewer = opts.get("reviewer_model") or writer
    if api_key and _provider(reviewer) != provider:
        raise HTTPException(400, "With a personal API key, writer and reviewer models must come from the same provider.")
    mock = provider == "mock"
    if not mock and not api_key and ACCESS_CODE and x_access_code != ACCESS_CODE:
        raise HTTPException(403, "Access code required to use the server's API key (or provide your own key).")
    if not form.get("method") or not (form.get("results") or result_files):
        raise HTTPException(400, "Method and experimental results are required.")
    if opts.get("template") not in list_templates():
        raise HTTPException(400, "unknown template")

    job_id = uuid.uuid4().hex[:12]
    jd = os.path.join(JOBS_DIR, job_id)
    up = os.path.join(jd, "uploads")
    total = [0]
    files = {
        "data": await _save_uploads(data_files, os.path.join(up, "data"), total),
        "results": await _save_uploads(result_files, os.path.join(up, "results"), total),
        "references": await _save_uploads(reference_files, os.path.join(up, "references"), total),
        "notes": await _save_uploads(note_files, os.path.join(up, "notes"), total),
    }
    figs = await _save_uploads(figure_files, os.path.join(up, "figures"), total)
    caps = p.get("figure_captions", {})
    files["figures"] = [(f, caps.get(os.path.basename(f), "")) for f in figs]
    form["authors"] = p.get("authors", [])
    form["declarations"] = p.get("declarations", {})
    form["venue_name"] = opts.get("venue_name", "")
    build_raw_materials(form, os.path.join(jd, "raw_materials"), files)

    cfg = JobConfig(
        template=opts["template"], writer_model=writer,
        reviewer_model=reviewer,
        api_keys={provider: api_key} if api_key else {},
        research_field=form.get("field") or "the target research field",
        venue_name=opts.get("venue_name", ""), language=opts.get("language", ""),
        anonymous=opts.get("anonymous"), cutoff=opts.get("cutoff", ""),
        title=form.get("title", ""), keywords=form.get("keywords", ""),
        authors=p.get("authors", []), declarations=p.get("declarations", {}),
        use_plotting=bool(opts.get("use_plotting", True)),
        refine_rounds=int(opts.get("refine_rounds", 2)), review_ensemble=int(opts.get("review_ensemble", 1)),
        format_check=bool(opts.get("format_check", True)), max_papers=int(opts.get("max_papers", 60)),
        mailto=opts.get("mailto", "") or os.environ.get("OPENALEX_MAILTO", ""),
        # Fake (offline) references are only allowed together with the mock model.
        offline_literature=mock)
    pipe = Pipeline(os.path.join(jd, "raw_materials"), jd, cfg)
    pipe._save()  # status.json = queued

    def _run():
        try:
            pipe.run()
        except Exception:  # noqa: BLE001  (status.json already records the failure)
            pass
    executor.submit(_run)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    jd = _job_dir(job_id)
    st = json.load(open(os.path.join(jd, "status.json"), encoding="utf-8"))
    return JSONResponse(st)  # config inside status is already masked (JobConfig.public)


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str, inline: bool = False):
    jd = _job_dir(job_id)
    rel = ALLOWED_DOWNLOADS.get(kind)
    if not rel or not os.path.exists(os.path.join(jd, rel)):
        raise HTTPException(404, "file not available")
    name = {"zip": f"paper_{job_id}.zip", "pdf": f"paper_{job_id}.pdf"}.get(kind, os.path.basename(rel))
    return FileResponse(os.path.join(jd, rel), filename=None if inline else name,
                        content_disposition_type="inline" if inline else "attachment")


@app.get("/api/jobs/{job_id}/preview/{n}")
def preview(job_id: str, n: int):
    jd = _job_dir(job_id)
    p = os.path.join(jd, "page_previews", f"grid_{int(n)}.png")
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p)


@app.post("/api/jobs/{job_id}/resume")
def resume(job_id: str, api_key: str = Form(""), x_access_code: str = Header("")):
    jd = _job_dir(job_id)
    st = json.load(open(os.path.join(jd, "status.json"), encoding="utf-8"))
    if st.get("state") == "running":
        raise HTTPException(409, "job is running")
    c = dict(st.get("config", {}))
    writer = c.get("writer_model", "claude-sonnet-5-5")
    provider = _provider(writer)
    if provider != "mock" and not api_key and ACCESS_CODE and x_access_code != ACCESS_CODE:
        raise HTTPException(403, "Access code required")
    c["api_keys"] = {provider: api_key} if api_key else {}
    c["s2_key"] = ""
    cfg = JobConfig(**{k: v for k, v in c.items() if k in JobConfig.__dataclass_fields__})
    pipe = Pipeline(os.path.join(jd, "raw_materials"), jd, cfg)
    executor.submit(lambda: pipe.run(resume=True))
    return {"ok": True}
