"""Ticket Triage Service - Assignment 1 baseline.

Deliberately naive: classification is synchronous, one blocking Ollama call
per ticket, no caching, no queuing, no retries.
"""

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

CATEGORIES = [
    "Credit reporting",
    "Debt collection",
    "Mortgage",
    "Credit card",
    "Bank account or service",
    "Consumer loan",
    "Money transfer or service",
]
UNCLASSIFIED = "unclassified"

MODEL = os.environ["MODEL"]
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "600"))
DB_PATH = os.environ.get("DB_PATH", "/data/tickets.db")
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

SYSTEM_PROMPT = (
    "You classify customer complaint tickets for a financial services company. "
    "Reply with exactly one of the following categories and nothing else:\n"
    + "\n".join(f"- {c}" for c in CATEGORIES)
)

# Filled in at startup.
model_digest = None
log_path = None
log_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tickets (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   narrative TEXT NOT NULL,
                   category TEXT NOT NULL,
                   model TEXT NOT NULL,
                   created_at TEXT NOT NULL
               )"""
        )


def pull_model_and_get_digest():
    """Make sure MODEL is present in Ollama and return its digest."""
    for _ in range(60):
        try:
            httpx.get(f"{OLLAMA_URL}/api/version", timeout=5)
            break
        except httpx.TransportError:
            time.sleep(2)
    else:
        raise RuntimeError(f"Ollama not reachable at {OLLAMA_URL}")

    r = httpx.post(
        f"{OLLAMA_URL}/api/pull", json={"model": MODEL, "stream": False}, timeout=None
    )
    r.raise_for_status()

    tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=30).json()["models"]
    for m in tags:
        if m["name"] in (MODEL, f"{MODEL}:latest"):
            return m["digest"]
    raise RuntimeError(f"Model {MODEL} not found in Ollama after pull")


def write_log(entry):
    with log_lock:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")


def parse_category(reply):
    """Return the category named earliest in the model's reply, if any."""
    text = reply.lower()
    found = [(text.find(c.lower()), c) for c in CATEGORIES if c.lower() in text]
    return min(found)[1] if found else UNCLASSIFIED


@asynccontextmanager
async def lifespan(app):
    global model_digest, log_path
    os.makedirs(LOG_DIR, exist_ok=True)
    init_db()
    model_digest = pull_model_and_get_digest()
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(
        LOG_DIR, f"{started}_{re.sub(r'[^A-Za-z0-9._-]', '-', MODEL)}.jsonl"
    )
    write_log(
        {
            "event": "startup",
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "model_digest": model_digest,
        }
    )
    yield


app = FastAPI(title="Ticket Triage Service", lifespan=lifespan)


@app.middleware("http")
async def log_request(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.log = {}
    start_epoch_ms = int(time.time() * 1000)
    t0 = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        write_log(
            {
                "event": "request",
                "ts": datetime.fromtimestamp(
                    start_epoch_ms / 1000, timezone.utc
                ).isoformat(),
                "start_epoch_ms": start_epoch_ms,
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
                **request.state.log,
            }
        )


class TicketIn(BaseModel):
    narrative: str = Field(min_length=1)


@app.post("/tickets")
def create_ticket(ticket: TicketIn, request: Request):
    log = request.state.log
    log.update(
        model=MODEL,
        model_digest=model_digest,
        narrative_chars=len(ticket.narrative),
    )

    try:
        r = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": ticket.narrative},
                ],
            },
            timeout=OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
        result = r.json()
    except httpx.HTTPError as e:
        log["error"] = f"{type(e).__name__}: {e}"
        return JSONResponse(status_code=502, content={"detail": "model backend error"})

    raw = result["message"]["content"]
    category = parse_category(raw)
    log.update(
        model_output=raw,
        category=category,
        # Ollama's own timings, in nanoseconds.
        ollama_total_duration_ns=result.get("total_duration"),
        ollama_load_duration_ns=result.get("load_duration"),
        ollama_prompt_eval_count=result.get("prompt_eval_count"),
        ollama_prompt_eval_duration_ns=result.get("prompt_eval_duration"),
        ollama_eval_count=result.get("eval_count"),
        ollama_eval_duration_ns=result.get("eval_duration"),
    )

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (narrative, category, model, created_at) VALUES (?, ?, ?, ?)",
            (ticket.narrative, category, MODEL, datetime.now(timezone.utc).isoformat()),
        )
        ticket_id = cur.lastrowid
    log["ticket_id"] = ticket_id

    return {"id": ticket_id, "category": category}


@app.get("/search")
def search(q: str, request: Request):
    with db() as conn:
        rows = conn.execute(
            "SELECT id, narrative, category, created_at FROM tickets "
            "WHERE narrative LIKE ? ORDER BY id",
            (f"%{q}%",),
        ).fetchall()
    request.state.log.update(query=q, results=len(rows))
    return {"query": q, "count": len(rows), "tickets": [dict(r) for r in rows]}


@app.get("/stats")
def stats():
    with db() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS n FROM tickets GROUP BY category"
        ).fetchall()
    counts = {c: 0 for c in CATEGORIES}
    counts.update({r["category"]: r["n"] for r in rows})
    return {"total": sum(counts.values()), "by_category": counts}
