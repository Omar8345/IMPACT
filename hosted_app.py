"""Hosted, non-executing public PR analyzer for IMPACT."""
import json
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

import github_pr
import graph
import main
import tools
from repo_parser import parse_repo

MAX_REPOSITORY_BYTES = int(os.getenv("IMPACT_MAX_REPOSITORY_BYTES", str(250 * 1024 * 1024)))
MAX_PYTHON_FILES = int(os.getenv("IMPACT_MAX_PYTHON_FILES", "1200"))
MAX_FILE_BYTES = int(os.getenv("IMPACT_MAX_FILE_BYTES", str(2 * 1024 * 1024)))
RESULT_TTL_SECONDS = int(os.getenv("IMPACT_RESULT_TTL_SECONDS", "3600"))
MAX_ACTIVE_JOBS = int(os.getenv("IMPACT_MAX_ACTIVE_JOBS", "2"))
RATE_LIMIT_SECONDS = int(os.getenv("IMPACT_RATE_LIMIT_SECONDS", "30"))
RESULT_ROOT = Path(os.getenv("IMPACT_RESULT_ROOT", "/tmp/impact-hosted-results"))

app = FastAPI(title="IMPACT public PR analyzer")
_executor = ThreadPoolExecutor(max_workers=MAX_ACTIVE_JOBS)
_jobs = {}
_jobs_lock = threading.Lock()
_last_submissions = {}


class AnalyzeRequest(BaseModel):
    url: str


def _expire_results():
    now = time.time()
    with _jobs_lock:
        expired = [job_id for job_id, job in _jobs.items()
                   if job.get("finished_at", now) + RESULT_TTL_SECONDS < now]
        for job_id in expired:
            job = _jobs.pop(job_id)
            shutil.rmtree(job.get("result_dir", ""), ignore_errors=True)


def _set_job(job_id, **values):
    with _jobs_lock:
        _jobs[job_id].update(values)


def _repository_limits(repo):
    total_bytes = 0
    python_files = 0
    for path in repo.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        size = path.stat().st_size
        total_bytes += size
        if size > MAX_FILE_BYTES:
            raise ValueError("This repository contains a file larger than the hosted limit.")
        if path.suffix == ".py":
            python_files += 1
        if total_bytes > MAX_REPOSITORY_BYTES:
            raise ValueError("This repository is larger than the hosted analysis limit.")
    if python_files > MAX_PYTHON_FILES:
        raise ValueError("This repository contains too many Python files for hosted analysis.")


def _analyze(job_id, url):
    result_dir = RESULT_ROOT / job_id
    result_dir.mkdir(parents=True, exist_ok=True)
    graph_name = f"impact_hosted_{job_id}"
    graph_obj = None
    try:
        _set_job(job_id, state="analyzing", message="Loading public PR metadata")
        pr = github_pr.get_pr(url)
        _set_job(job_id, message=f"Checking out commit {pr['head_sha'][:12]}")
        with github_pr.checkout_pr(pr) as (repo, diff):
            _repository_limits(repo)
            _set_job(job_id, message="Parsing Python functions and call edges")
            funcs, edges = parse_repo(repo)
            if not funcs:
                raise ValueError("This PR does not contain a supported Python call graph.")
            _set_job(job_id, message="Loading an isolated impact graph")
            graph_obj = graph.connect(graph_name)
            graph.load(graph_obj, funcs, edges)
            tools.set_graph(graph_obj)
            args = SimpleNamespace(
                hops=4, llm=os.getenv("IMPACT_HOSTED_LLM", "false").lower() in {"1", "true", "yes"},
                run_tests=False, test_command=None, restricted_env=True,
                html=str(result_dir / "impact.html"), report=str(result_dir / "impact-report.md"),
            )
            _set_job(job_id, message="Following possible impact paths")
            report = main.produce_review(repo, diff, args, graph_obj=graph_obj)
            if not report:
                raise ValueError("No changed Python function was found in this PR.")
            metadata = {"url": pr["url"], "repository": f"{pr['owner']}/{pr['repo']}",
                        "number": pr["number"], "head_sha": pr["head_sha"],
                        "graph": graph_name, "tests_run": False}
            (result_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        _set_job(job_id, state="complete", message="Report ready", finished_at=time.time(),
                 result_dir=str(result_dir), result_url=f"/results/{job_id}")
    except Exception as exc:
        _set_job(job_id, state="failed", message=str(exc), finished_at=time.time(),
                 result_dir=str(result_dir))
    finally:
        if graph_obj is not None:
            try:
                graph_obj.delete()
            except Exception:
                pass


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)


@app.post("/api/analyze")
def create_analysis(request: AnalyzeRequest, http_request: Request):
    _expire_results()
    try:
        github_pr.parse_pr_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    client = http_request.client.host if http_request.client else "unknown"
    now = time.time()
    with _jobs_lock:
        if now - _last_submissions.get(client, 0) < RATE_LIMIT_SECONDS:
            raise HTTPException(status_code=429, detail="Please wait before starting another analysis.")
        _last_submissions[client] = now
    with _jobs_lock:
        active = sum(job["state"] in {"queued", "analyzing"} for job in _jobs.values())
        if active >= MAX_ACTIVE_JOBS:
            raise HTTPException(status_code=429, detail="Hosted analysis capacity is currently full.")
        job_id = uuid.uuid4().hex
        _jobs[job_id] = {"state": "queued", "message": "Waiting for an analysis worker"}
    _executor.submit(_analyze, job_id, request.url)
    return {"id": job_id, "status_url": f"/api/analyze/{job_id}"}


@app.get("/api/analyze/{job_id}")
def analysis_status(job_id: str):
    _expire_results()
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Analysis not found or expired.")
        return {key: value for key, value in job.items() if key != "result_dir"}


@app.get("/results/{job_id}", response_class=HTMLResponse)
def result_page(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job.get("state") != "complete":
        raise HTTPException(status_code=404, detail="Report not found or still processing.")
    report = Path(job["result_dir"]) / "impact.html"
    if not report.is_file():
        raise HTTPException(status_code=404, detail="Report expired.")
    html = report.read_text(encoding="utf-8")
    download = (f'<p style="padding:12px 24px;font-family:ui-monospace,monospace">'
                f'<a href="/results/{job_id}/download">Download Markdown report</a></p>')
    return HTMLResponse(html.replace("</header>", download + "</header>", 1))


@app.get("/results/{job_id}/download", response_class=PlainTextResponse)
def download_report(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job.get("state") != "complete":
        raise HTTPException(status_code=404, detail="Report not found or still processing.")
    report = Path(job["result_dir"]) / "impact-report.md"
    if not report.is_file():
        raise HTTPException(status_code=404, detail="Report expired.")
    return PlainTextResponse(report.read_text(encoding="utf-8"),
                             headers={"Content-Disposition": f"attachment; filename=impact-{job_id}.md"})


INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IMPACT / public PR analysis</title><style>
:root{color-scheme:dark;--bg:#101314;--panel:#191e1f;--line:#364041;--ink:#f3f1e9;--muted:#a5adab;--accent:#ff5b68;--mint:#66d6b3}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#101314,#182022);color:var(--ink);font:16px/1.5 Georgia,serif}main{width:min(920px,calc(100% - 32px));margin:auto;padding:10vh 0}h1{font:800 clamp(42px,8vw,84px)/.94 ui-sans-serif,system-ui;margin:14px 0;letter-spacing:-.04em}p{color:var(--muted)}.eyebrow{color:var(--accent);font:700 12px ui-monospace,monospace;letter-spacing:.18em;text-transform:uppercase}.form{display:flex;gap:10px;margin-top:34px}.form input{flex:1;min-width:0;background:var(--panel);border:1px solid var(--line);padding:17px;color:var(--ink);font:16px ui-monospace,monospace}.form button{background:var(--accent);border:0;padding:0 22px;color:#180d0e;font-weight:800;cursor:pointer}.status{margin-top:22px;min-height:28px;color:var(--mint);font-family:ui-monospace,monospace}.limits{border-top:1px solid var(--line);margin-top:64px;padding-top:18px;font-size:14px}@media(max-width:600px){main{padding:48px 0}.form{display:block}.form button{width:100%;height:54px;margin-top:10px}}
</style></head><body><main><div class="eyebrow">Graph intelligence / public analyzer</div><h1>What does this PR affect?</h1><p>Paste a public GitHub pull-request URL. IMPACT checks the exact head commit, maps Python call paths in FalkorDB, and returns a review you can share.</p><form class="form" id="form"><input id="url" type="url" required placeholder="https://github.com/owner/repo/pull/123"><button>Analyze PR</button></form><div class="status" id="status" role="status"></div><div class="limits">Public GitHub PRs only. Hosted analysis parses code but never runs repository code or tests. Results expire after a short period.</div></main><script>
const form=document.querySelector('#form'),status=document.querySelector('#status');form.addEventListener('submit',async e=>{e.preventDefault();status.textContent='Queueing analysis...';try{const r=await fetch('/api/analyze',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url:document.querySelector('#url').value})});const data=await r.json();if(!r.ok)throw Error(data.detail||'Unable to queue analysis');while(true){await new Promise(resolve=>setTimeout(resolve,1200));const s=await fetch(data.status_url).then(x=>x.json());status.textContent=s.message||s.state;if(s.state==='complete'){location.href=s.result_url;break}if(s.state==='failed')throw Error(s.message)}}catch(err){status.textContent='Error: '+err.message}});
</script></body></html>"""
