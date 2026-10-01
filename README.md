# ICT3113 Assignment 1 - Ticket Triage Service (baseline)

A web service that classifies financial complaint tickets into seven categories
using a local Ollama model on CPU.

This is the unoptimised Assignment 1 baseline: classification is synchronous,
with one blocking model call per ticket and no caching, queuing or retries.

## Run

```sh
MODEL=qwen2.5:0.5b docker compose up -d --build
```

`MODEL` is the Ollama tag of the candidate model. The service pulls it on
startup, so the first start of a new model takes a while. Follow progress with
`docker compose logs -f triage`; the service is ready when it prints
`Application startup complete`.

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
docker compose down
docker volume rm "$(docker volume ls -q | grep triage-data)"
MODEL=<tag> docker compose up -d
```

`docker compose down -v` also works, but it deletes the downloaded models too.

## Logs

Every request is logged as one JSON line in `logs/`. Each service start opens a
new file named `<UTC start time>_<model>.jsonl`, whose first line records the
model tag and digest. Request lines contain:

- `ts`, `start_epoch_ms`, `request_id`, `method`, `path`, `status`, `latency_ms`
- for `POST /tickets`: `model`, `model_digest`, `narrative_chars`,
  `model_output`, `category`, `ticket_id`, and Ollama's own timings
  (`ollama_*_duration_ns`, token counts)
- for `GET /search`: `query`, `results`

The response carries an `X-Request-ID` header. If the caller sends its own
`X-Request-ID`, that value is used, which lets JMeter samples be matched to log
lines.
