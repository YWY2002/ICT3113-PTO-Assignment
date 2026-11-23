"""Ticket Triage Service.

Assignment 1 baseline: one Ollama call per ticket, chosen by OLLAMA_API=chat
or systemone.

Assignment 2 cascade: OLLAMA_API=cascade sends every ticket to CASCADE_SMALL
first; if its answer is in CASCADE_RISKY (or unreadable), the ticket is
re-classified by CASCADE_LARGE and the large model's answer is final. Both
models stay resident; the caller still sees one category.
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
# chat (/api/chat), systemone (/v1/systemone), or cascade (two models + rule).
OLLAMA_API = os.environ.get("OLLAMA_API", "chat")
if OLLAMA_API not in ("chat", "systemone", "cascade"):
    raise RuntimeError(f"OLLAMA_API must be 'chat', 'systemone' or 'cascade', not {OLLAMA_API!r}")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "600"))
DB_PATH = os.environ.get("DB_PATH", "/data/tickets.db")
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

# Cascade config. Only read when OLLAMA_API == "cascade".
CASCADE_SMALL = os.environ.get("CASCADE_SMALL", "")
CASCADE_SMALL_API = os.environ.get("CASCADE_SMALL_API", "systemone")
CASCADE_LARGE = os.environ.get("CASCADE_LARGE", "")
CASCADE_LARGE_API = os.environ.get("CASCADE_LARGE_API", "systemone")
# Comma-separated list of category names. If small model's answer is in this
# set (or UNCLASSIFIED), the ticket is escalated to the large model.
CASCADE_RISKY_RAW = os.environ.get("CASCADE_RISKY", "")
CASCADE_RISKY = {s.strip() for s in CASCADE_RISKY_RAW.split(",") if s.strip()}

if OLLAMA_API == "cascade":
    if not CASCADE_SMALL or not CASCADE_LARGE:
        raise RuntimeError("OLLAMA_API=cascade requires CASCADE_SMALL and CASCADE_LARGE")
    if CASCADE_SMALL_API not in ("chat", "systemone"):
        raise RuntimeError(f"CASCADE_SMALL_API must be 'chat' or 'systemone', not {CASCADE_SMALL_API!r}")
    if CASCADE_LARGE_API not in ("chat", "systemone"):
        raise RuntimeError(f"CASCADE_LARGE_API must be 'chat' or 'systemone', not {CASCADE_LARGE_API!r}")
    unknown = CASCADE_RISKY - set(CATEGORIES)
    if unknown:
        raise RuntimeError(f"CASCADE_RISKY contains unknown categories: {sorted(unknown)}")

SYSTEM_PROMPT = (
    "You classify customer complaint tickets for a financial services company. "
    "Reply with exactly one of the following categories and nothing else:\n"
    + "\n".join(f"- {c}" for c in CATEGORIES)
)

SYSTEMONE_QUESTION = {
    "type": "choice",
    "instructions": (
        "Which category does this customer complaint ticket for a "
        "financial services company belong to?"
    ),
    "criteria": {c: c for c in CATEGORIES},
}

# Filled in at startup.
model_digest = None       # for chat/systemone: MODEL's digest. For cascade: None.
cascade_small_digest = None
cascade_large_digest = None
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


def wait_for_ollama():
    for _ in range(60):
        try:
            httpx.get(f"{OLLAMA_URL}/api/version", timeout=5)
            return
        except httpx.TransportError:
            time.sleep(2)
    raise RuntimeError(f"Ollama not reachable at {OLLAMA_URL}")


def pull_and_get_digest(tag):
    """Make sure `tag` is present in Ollama and return its digest."""
    r = httpx.post(
        f"{OLLAMA_URL}/api/pull", json={"model": tag, "stream": False}, timeout=None
    )
    r.raise_for_status()
    tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=30).json()["models"]
    for m in tags:
        if m["name"] in (tag, f"{tag}:latest"):
            return m["digest"]
    raise RuntimeError(f"Model {tag} not found in Ollama after pull")


def write_log(entry):
    with log_lock:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")


def parse_category(reply):
    """Return the category named earliest in the model's reply, if any."""
    text = reply.lower()
    found = [(text.find(c.lower()), c) for c in CATEGORIES if c.lower() in text]
    return min(found)[1] if found else UNCLASSIFIED


def ollama_timings(result):
    return {
        "ollama_total_duration_ns": result.get("total_duration"),
        "ollama_load_duration_ns": result.get("load_duration"),
        "ollama_prompt_eval_count": result.get("prompt_eval_count"),
        "ollama_prompt_eval_duration_ns": result.get("prompt_eval_duration"),
        "ollama_eval_count": result.get("eval_count"),
        "ollama_eval_duration_ns": result.get("eval_duration"),
    }


def classify_chat(narrative, tag):
    r = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": tag,
            "stream": False,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": narrative},
            ],
        },
        timeout=OLLAMA_TIMEOUT,
    )
    r.raise_for_status()
    result = r.json()
    raw = result["message"]["content"]
    return raw, parse_category(raw), ollama_timings(result)


def classify_systemone(narrative, tag):
    r = httpx.post(
        f"{OLLAMA_URL}/v1/systemone",
        json={
            "model": tag,
            "state": narrative,
            "questions": {"category": SYSTEMONE_QUESTION},
        },
        timeout=OLLAMA_TIMEOUT,
    )
    r.raise_for_status()
    result = r.json()
    answer = result["answers"]["category"]
    choice = answer.get("choice")
    category = choice if choice in CATEGORIES else UNCLASSIFIED
    fields = ollama_timings(result)
    usage = result.get("usage") or {}
    if fields["ollama_prompt_eval_count"] is None:
        fields["ollama_prompt_eval_count"] = usage.get("input_tokens")
    if fields["ollama_eval_count"] is None:
        fields["ollama_eval_count"] = usage.get("output_tokens")
    fields["choice_confidence"] = answer.get("confidence")
    return json.dumps(answer), category, fields


def _call(api, narrative, tag):
    if api == "chat":
        return classify_chat(narrative, tag)
    return classify_systemone(narrative, tag)


def classify_single(narrative):
    """Assignment 1 single-model path."""
    raw, category, fields = _call(OLLAMA_API, narrative, MODEL)
    fields["final_model"] = MODEL
    fields["escalated"] = False
    return raw, category, fields


def classify_cascade(narrative):
    """Assignment 2 cascade. Returns (raw of final model, final category, log fields).

    Rule: run CASCADE_SMALL first. If its answer is in CASCADE_RISKY, or the
    answer is UNCLASSIFIED (unreadable), escalate to CASCADE_LARGE and use
    the large model's answer. Otherwise accept the small model's answer.
    """
    t0 = time.perf_counter()
    small_raw, small_cat, small_fields = _call(CASCADE_SMALL_API, narrative, CASCADE_SMALL)
    small_latency_ms = round((time.perf_counter() - t0) * 1000, 3)

    escalated = small_cat == UNCLASSIFIED or small_cat in CASCADE_RISKY

    log = {
        "small_model": CASCADE_SMALL,
        "small_model_digest": cascade_small_digest,
        "small_api": CASCADE_SMALL_API,
        "small_category": small_cat,
        "small_latency_ms": small_latency_ms,
        "small_confidence": small_fields.get("choice_confidence"),
        "small_output": small_raw,
        "small_ollama_total_duration_ns": small_fields.get("ollama_total_duration_ns"),
        "small_ollama_prompt_eval_count": small_fields.get("ollama_prompt_eval_count"),
        "small_ollama_eval_count": small_fields.get("ollama_eval_count"),
    }

    if not escalated:
        log["escalated"] = False
        log["final_model"] = CASCADE_SMALL
        log["model_digest"] = cascade_small_digest
        # Keep the top-level ollama_* fields pointing at the model whose answer
        # was returned (matches single-model semantics for analysis).
        for k in (
            "ollama_total_duration_ns",
            "ollama_load_duration_ns",
            "ollama_prompt_eval_count",
            "ollama_prompt_eval_duration_ns",
            "ollama_eval_count",
            "ollama_eval_duration_ns",
        ):
            log[k] = small_fields.get(k)
        log["choice_confidence"] = small_fields.get("choice_confidence")
        return small_raw, small_cat, log

    t1 = time.perf_counter()
    large_raw, large_cat, large_fields = _call(CASCADE_LARGE_API, narrative, CASCADE_LARGE)
    large_latency_ms = round((time.perf_counter() - t1) * 1000, 3)

    log.update(
        large_model=CASCADE_LARGE,
        large_model_digest=cascade_large_digest,
        large_api=CASCADE_LARGE_API,
        large_category=large_cat,
        large_latency_ms=large_latency_ms,
        large_confidence=large_fields.get("choice_confidence"),
        large_output=large_raw,
        large_ollama_total_duration_ns=large_fields.get("ollama_total_duration_ns"),
        large_ollama_prompt_eval_count=large_fields.get("ollama_prompt_eval_count"),
        large_ollama_eval_count=large_fields.get("ollama_eval_count"),
        escalated=True,
        final_model=CASCADE_LARGE,
        model_digest=cascade_large_digest,
        choice_confidence=large_fields.get("choice_confidence"),
    )
    for k in (
        "ollama_total_duration_ns",
        "ollama_load_duration_ns",
        "ollama_prompt_eval_count",
        "ollama_prompt_eval_duration_ns",
        "ollama_eval_count",
        "ollama_eval_duration_ns",
    ):
        log[k] = large_fields.get(k)
    return large_raw, large_cat, log


classify = classify_cascade if OLLAMA_API == "cascade" else classify_single


@asynccontextmanager
async def lifespan(app):
    global model_digest, cascade_small_digest, cascade_large_digest, log_path
    os.makedirs(LOG_DIR, exist_ok=True)
    init_db()
    wait_for_ollama()
    if OLLAMA_API == "cascade":
        cascade_small_digest = pull_and_get_digest(CASCADE_SMALL)
        cascade_large_digest = pull_and_get_digest(CASCADE_LARGE)
    else:
        model_digest = pull_and_get_digest(MODEL)
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(
        LOG_DIR, f"{started}_{re.sub(r'[^A-Za-z0-9._-]', '-', MODEL)}.jsonl"
    )
    startup = {
        "event": "startup",
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "ollama_api": OLLAMA_API,
    }
    if OLLAMA_API == "cascade":
        startup.update(
            cascade_small=CASCADE_SMALL,
            cascade_small_digest=cascade_small_digest,
            cascade_small_api=CASCADE_SMALL_API,
            cascade_large=CASCADE_LARGE,
            cascade_large_digest=cascade_large_digest,
            cascade_large_api=CASCADE_LARGE_API,
            cascade_risky=sorted(CASCADE_RISKY),
        )
    else:
        startup["model_digest"] = model_digest
    write_log(startup)
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
        ollama_api=OLLAMA_API,
        narrative_chars=len(ticket.narrative),
    )

    try:
        raw, category, fields = classify(ticket.narrative)
    except httpx.HTTPError as e:
        log["error"] = f"{type(e).__name__}: {e}"
        return JSONResponse(status_code=502, content={"detail": "model backend error"})

    log.update(model_output=raw, category=category, **fields)

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (narrative, category, model, created_at) VALUES (?, ?, ?, ?)",
            (ticket.narrative, category, fields.get("final_model", MODEL), datetime.now(timezone.utc).isoformat()),
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
