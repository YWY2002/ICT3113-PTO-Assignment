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

## Load tests (JMeter, open loop, two machines)

The load generator and the system under test (SUT) run on separate machines.
The SUT runs Docker and Ollama; the load generator needs only the `loadtest/`
folder and the JMeter **binary** release (5.6.3) on `PATH` as `jmeter.bat`
(or pass `-JMeter <path to jmeter.bat>`).

**One-time setup**

- SUT: build the input files (rows 5000 to 5999), then copy `loadtest/` to the
  load generator: `python loadtest/prepare_data.py`
- SUT: allow port 8000 in (administrator PowerShell; remove after testing):
  `New-NetFirewallRule -DisplayName "Triage service 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private`
- Load generator: check the SUT answers: `curl http://<SUT IP>:8000/stats`

**Each run (three per configuration)**

| Step | Machine | Command |
|---|---|---|
| 1 | SUT | `.\loadtest\sut_prepare.ps1 -Model tev1:4b -Api systemone -Test mixed -Run 1` (wait for `READY`) |
| 2 | Load generator | `.\loadtest\loadgen_run.ps1 -SutHost <SUT IP> -Model tev1:4b -Test mixed -Run 1 -PostPerHour 198 -SearchPerHour 800` |
| 3 | SUT | copy the load generator's `results/<model>/<test>/run<N>/` folder over, then `.\loadtest\sut_collect.ps1 -Model tev1:4b -Test mixed -Run 1 -LoadgenDir <copied folder>` |

Configurations: `-Test mixed -PostPerHour 198 -SearchPerHour 800` (R2 and R3)
and `-Test surge -PostPerHour 334` (R1). The stress test passes a stepped
`-PostSchedule`; see the examples in `loadgen_run.ps1`.

**What each run folder holds** (`results/<model>/<test>/run<N>/` on the SUT)

| File | From | Contents |
|---|---|---|
| `results.jtl` | load generator | every JMeter sample, with `req_id`, `row`, `term` |
| `loadgen.json`, `run.properties`, `jmeter.log` | load generator | schedules, start/end times, load generator hardware, ping round-trip time |
| `service.jsonl` | SUT | the service log for this run |
| `cpu.csv` | SUT | CPU utilisation every 5 s: total, Ollama processes, Docker's WSL VM |
| `ollama_ps.txt` | SUT | confirms the model is loaded 100% on CPU |
| `sut_start.json`, `metadata.json` | SUT | model digest, git commit, Ollama version, sample and log line counts |

Every JMeter sample sends a unique `X-Request-ID` (`t-...` for tickets, `s-...`
for searches), saved as `req_id` in the `.jtl` and as `request_id` in the
service log, so samples and log lines match one-to-one even though they are
recorded on different machines. The warm-up request is logged as `warmup`.

## Accuracy tests (golden set)

Sends all 150 golden tickets through `POST /tickets`, one at a time, and scores
the service log against the golden labels (requirement R4). Run everything on
the SUT; no JMeter needed. Needs `pandas` and `openpyxl`.

```powershell
.\loadtest\sut_prepare.ps1 -Model tev1:4b -Api systemone -Test accuracy -Run 1   # wait for READY
python accuracy\send_golden.py --model tev1:4b --run 1
.\loadtest\sut_collect.ps1 -Model tev1:4b -Test accuracy -Run 1
python accuracy\score_accuracy.py --model tev1:4b --run 1
```

Each ticket is sent with `X-Request-ID: golden-<row>`. Because tickets are sent
sequentially there is no queueing, so the latency in these runs is each model's
single-request service time.

`score_accuracy.py` writes into `results/<model>/accuracy/run<N>/`:

| File | Contents |
|---|---|
| `report.md` | R4 verdict, overall accuracy with 95% Wilson interval, per-category recall and precision, confusion matrix, most frequent confusions, single-request latency (nearest-rank p50/p95/p99) and output tokens |
| `predictions.csv` | per golden row: golden label, predicted category, latency, tokens, raw model output |
| `confusion_matrix.csv`, `per_category.csv` | the tables behind the report |

Run `python accuracy\score_accuracy.py` with no arguments to rescore every
accuracy run and write `results/accuracy_summary.csv` (one line per model and
run, for the slides).
