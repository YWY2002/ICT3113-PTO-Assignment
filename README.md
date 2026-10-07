# ICT3113 Assignment 1 - Ticket Triage Service (baseline)

A web service that classifies financial complaint tickets into seven categories
using a local Ollama model on CPU.

This is the unoptimised Assignment 1 baseline: classification is synchronous,
with one blocking model call per ticket and no caching, queuing or retries.

## Run

Ollama runs natively on the host (Ollama 0.40.0 on Windows), not in Docker;
the service reaches it at `host.docker.internal:11434`. Start Ollama first.

```sh
MODEL=qwen3.8:27b OLLAMA_API=chat docker compose up -d --build
MODEL=tev1:4b OLLAMA_API=systemone docker compose up -d --build
```

In PowerShell, set the variables first:
`$env:MODEL='tev1:4b'; $env:OLLAMA_API='systemone'; docker compose up -d --build`

`MODEL` is the Ollama tag of the candidate model. The service pulls it on
startup, so the first start of a new model takes a while. Follow progress with
`docker compose logs -f triage`; the service is ready when it prints
`Application startup complete`.

`OLLAMA_API` selects how tickets are classified:

| `OLLAMA_API` | Endpoint | Use for |
|---|---|---|
| `chat` (default) | `/api/chat`, system prompt listing the categories | generative models, e.g. `qwen3.8:27b` |
| `systemone` | `/v1/systemone`, one `choice` question whose options are the categories | decision models `tev1:4b`, `clef-flash:9b` |

Both paths send the same information (the seven category names) and make one
synchronous call per ticket.

The service listens on port 8000.

## Endpoints

| Endpoint | What it does |
|---|---|
| `POST /tickets` | Body `{"narrative": "..."}`. Classifies the ticket, stores it, returns `{"id", "category"}`. |
| `GET /search?q=text` | Returns stored tickets whose narrative contains `text`. |
| `GET /stats` | Returns counts of stored tickets by category. |

If the model's reply names none of the seven categories, the ticket is stored
as `unclassified`.

```sh
curl -X POST localhost:8000/tickets -H 'Content-Type: application/json' \
  -d '{"narrative": "A collector keeps calling me about a debt I already paid."}'
curl 'localhost:8000/search?q=collector'
curl localhost:8000/stats
```

## Data and resetting between runs

Stored tickets live in the `triage-data` Docker volume, so they survive
restarts and rebuilds. The service must start empty for each test run:

```sh
docker compose down -v
MODEL=<tag> OLLAMA_API=<chat|systemone> docker compose up -d
```

Models are stored by the host's Ollama, so `down -v` only deletes the ticket
database.

## Logs

Every request is logged as one JSON line in `logs/`. Each service start opens a
new file named `<UTC start time>_<model>.jsonl`, whose first line records the
model tag and digest. Request lines contain:

- `ts`, `start_epoch_ms`, `request_id`, `method`, `path`, `status`, `latency_ms`
- for `POST /tickets`: `model`, `model_digest`, `ollama_api`, `narrative_chars`,
  `model_output`, `category`, `ticket_id`, and Ollama's own timings
  (`ollama_*_duration_ns`, token counts). `/v1/systemone` returns only token
  counts, so its duration fields are `null`; it also logs `choice_confidence`.
- for `GET /search`: `query`, `results`

The response carries an `X-Request-ID` header. If the caller sends its own
`X-Request-ID`, that value is used, which lets JMeter samples be matched to log
lines.

## Load tests (JMeter, open loop)

Requires the JMeter **binary** release (5.6.3) on `PATH` as `jmeter.bat`, or
pass `-JMeter <path to jmeter.bat>`.

1. Build the input files once (rows 5000 to 5999):
   `python loadtest/prepare_data.py`
2. Run one configuration per command. Each run restarts the service with an
   empty database, sends a warm-up ticket, then runs `loadtest/triage.jmx`:

   ```powershell
   # R2 + R3: 198 tickets/h with 800 searches/h, 60 min
   .\loadtest\run_test.ps1 -Model tev1:4b -Api systemone -Test mixed -Run 1 -PostPerHour 198 -SearchPerHour 800
   # R1: 334 tickets/h, 60 min
   .\loadtest\run_test.ps1 -Model tev1:4b -Api systemone -Test surge -Run 1 -PostPerHour 334
   ```

Results go to `results/<model>/<test>/run<N>/`: `results.jtl`, the matching
`service.jsonl`, `metadata.json` (model digest, schedules, git commit, Ollama
version) and `ollama_ps.txt` (confirms the model ran 100% on CPU). Every JMeter
sample sends a unique `X-Request-ID` (`t-…` for tickets, `s-…` for searches),
saved as `req_id` in the `.jtl` and as `request_id` in the service log; the
warm-up request is logged as `warmup`.
