"""Public access to fixed synthetic reports only; no clinical database or credentials.

Run as a separate single-worker service. Only the existing bounded demo reader
can invoke Ollama. A global budget protects the shared GPU across visitor quotas.
"""
import os
import threading
import time
from collections import deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from . import demo_reader as reader

ORIGIN = "https://clinloopai.app"
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
_recent = deque()
_lock = threading.Lock()


@app.middleware("http")
async def restrict_requests(request: Request, call_next):
    from starlette.responses import JSONResponse
    origin = request.headers.get("origin")
    if origin and origin != ORIGIN:
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    # No free text, uploads or prompt bodies may enter this service.
    if request.method == "POST":
        async for chunk in request.stream():
            if chunk:
                return JSONResponse({"detail": "This demo accepts catalogue IDs only"}, status_code=400)
    return await call_next(request)


def _case(case_id):
    c = reader.case(case_id)
    if c is None:
        raise HTTPException(404, "No such synthetic report")
    return c


@app.get("/health")
def health():
    return {"status": "ok", "scope": "fixed synthetic reports only"}


@app.get("/api/v1/demo/reports")
def reports():
    cat = reader.catalog()
    return {"note": cat["note"], "model": cat["model"],
            "cases": [{k: c[k] for k in ("id", "title", "language", "teaches")} for c in cat["cases"]]}


@app.get("/api/v1/demo/reports/{case_id}")
def report(case_id: str):
    c = _case(case_id)
    rules = reader.rules_for(c)
    saved = dict(c["saved_reading"], items=reader.compare(rules, c["saved_reading"]["items"]))
    return {**{k: c[k] for k in ("id", "title", "date", "language", "patient", "text", "teaches")},
            "rules": rules, "model_reading": saved, "model": reader.catalog()["model"]}


@app.post("/api/v1/demo/reports/{case_id}/live")
async def live(case_id: str, request: Request):
    c = _case(case_id)
    now = time.monotonic()
    with _lock:
        while _recent and now - _recent[0] >= 3600:
            _recent.popleft()
        if len(_recent) >= int(os.environ.get("CLINLOOP_PUBLIC_READS_PER_HOUR", "12")):
            raise HTTPException(429, "The shared demo limit is reached. Saved readings remain available.")
        _recent.append(now)
    # Only the tunnel can reach this container over its dedicated Docker network.
    visitor = request.headers.get("cf-connecting-ip") or request.client.host
    try:
        out = await run_in_threadpool(reader.live_read, c, visitor)
    except reader.Busy:
        raise HTTPException(429, "The model is busy or your demo quota is reached. Try later.")
    if not out.get("available"):
        raise HTTPException(503, "The local model is temporarily unavailable. Use the saved reading.")
    out["items"] = reader.compare(reader.rules_for(c), out["items"])
    out["live_left_this_hour"] = reader.quota_left(visitor)
    return out
