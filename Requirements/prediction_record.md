# Prediction Record

Predictions are stated so they can be shown wrong by the service logs (`logs/*.jsonl`) and the JMeter `.jtl` files.

Workload figures come from the [workload model](../WorkloadModel/workload_model.md), cited as WM §n with a link to the section. Requirement IDs (R1 to R4) refer to [Requirements.md](Requirements.md).

**Assumed system under test** Ollama and the triage service run on an AMD Ryzen 7 4800HS, 16GB RAM, dual-channel DDR4-3200, Windows 11, CPU only. 

## System Hardware Specifications
- AMD Ryzen 7 4800HS
  - 8 cores / 16 threads
  - 2.9GHz base speed, up to 4.2GHz overclock speed
  - Zen 2 (Renoir) architecture with Socket FP6
  - Uses Advanced Vector Extensions (AVX), including newer AVX2 standard, too, but not AVX-512
- RAM
  - Total installed 2 X 8GB (15.4GB usable)
  - DDR4-3200


## 1. How the latency predictions were made

Service time is estimated with an execution model:

S ≈ prompt tokens / prefill rate + output tokens / decode rate + fixed overhead

- **Prompt tokens.** These are (ticket characters + instruction characters) / 4, using 4 characters per token ([WM §4](../WorkloadModel/workload_model.md#4-ticket-length), `characters_per_token`). Ticket lengths are the median of 802 characters, the mean of 883 and the p95 of 1,772 (same section).
  - `/api/chat` path (Qwen3.8): 274 instruction characters ([WM §4](../WorkloadModel/workload_model.md#4-ticket-length), `prompt_characters`) plus chat template. That is about 284 tokens at the median ticket and about 510 at p95.
  - `/v1/systemone` path (Tev1, Clef Flash): we assume about 1,200 characters of question, instructions and criteria for the 7 categories. This is our assumption, not a workload-model figure. That is about 500 tokens at the median and about 740 at p95.
- **Prefill rate.** Prefill is compute-bound: about 2 × parameters FLOPs per token on 8 Zen 2 cores. Estimated rates are 70 tokens/s for 4B, 30 for 9B and 10 for 27B.
- **Decode rate.** Decode is memory-bandwidth-bound: about 35 GB/s effective divided by model size, so about 2 tokens/s for the 18 GB Qwen3.8. Tev1 and Clef Flash score options in a single pass, so they have no decode phase.
- **Fixed overhead.** About 0.3 s for HTTP, JSON and SQLite.

## 2. Where the bottleneck will be

**B1. Ollama CPU inference is the capacity bottleneck for every candidate.** Specifically:
- At low load, Ollama time (`ollama_total_duration_ns`) is **≥ 95%** of `latency_ms` for every successful `POST /tickets`.
- Prefill, not decode, dominates Ollama time for Tev1 and Clef Flash (`ollama_prompt_eval_duration_ns` is at least 80% of `ollama_total_duration_ns`).
- During inference, Ollama CPU utilisation is **≥ 90%** of all cores. Triage-service CPU stays **< 5%**.
- SQLite insert time is below 10 ms and never the bottleneck.

**B2. Queueing happens in front of Ollama, not in FastAPI.** Ollama processes one request at a time. Waiting time, measured as `latency_ms` − Ollama time, stays near zero below ρ = 0.5, then grows sharply. At ρ ≥ 0.7 it exceeds S.

**B3. Overload cascades through the 40-thread pool and the 600 s timeout.** When arrivals exceed 1/S, the queue grows by (λ − 1/S) tickets per hour. By Little's Law (n = λR):
- **Timeouts.** Once a request's response time would pass 600 s (`OLLAMA_TIMEOUT`), `POST /tickets` starts returning **502**. This is lost work.
- **Thread starvation.** Once more than 40 requests are in flight, FastAPI's thread pool is exhausted. **`GET /search` and `GET /stats` then queue behind classification**, even though they never touch Ollama.

**Why.** Inference demand (seconds) exceeds every other demand by about three orders of magnitude, so by bottleneck analysis Ollama saturates first.

## 3. Per-model predictions

| | `tev1:4b` | `clef-flash:9b` | `qwen3.8:27b` |
|---|---:|---:|---:|
| **Overall accuracy on golden set** | **72%** (108/150) | **78%** (117/150) | **83%** (125/150), if it runs |
| `unclassified` rate | ≤ 2% | ≤ 2% | 5% to 15% with thinking on |
| **Single-request latency, p50** | **7.4 s** | **17 s** | does not load (see Q1); about 32 s on a 32 GB+ host with thinking off |
| Single-request latency, p95 | 11 s | 25 s | about 57 s on a 32 GB+ host with thinking off |
| Throughput ceiling (3600 / mean S) | about 465 tickets/h | about 205 tickets/h | about 105 tickets/h |
| R1 (surge 334/h, [WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods)) | **Pass, borderline**: ρ ≈ 0.72, mean R ≈ 18 s | **Fail**: ρ ≈ 1.64; 502s from about 16 min; thread pool full from about 18 min | **Fail** |
| R2 (p95 ≤ 10 s at 198/h, [WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods)) | **Fail, narrowly**: p95 ≈ 12 to 14 s | **Fail**: ρ ≈ 0.97, mean R about 5 min | **Fail** |
| R4 (≥ 80% overall) | **Fail** | **Borderline fail** | **Pass**, if it runs |

Latency p50 and p95 use the median (802) and p95 (1,772) ticket lengths, and the throughput ceiling uses the mean (883), all from [WM §4](../WorkloadModel/workload_model.md#4-ticket-length). R1 and R2 queueing figures apply Kingman at the arrival rates in [WM §2](../WorkloadModel/workload_model.md#tickets-per-hour).

Accuracy reasoning:
- **Tev1 4B.** Its published mean accuracy across 13 human-labelled datasets is 73.3%, and it was trained on banking data. We expect about the same here.
- **Clef Flash 9B.** A larger model of the same family as Tev1, so we expect higher accuracy.
- **Qwen3.8 27B.** The largest model, but capped by the 84.7% human agreement on this set.

**Model-specific predictions:**

- **Q1. Qwen3.8 27B will not fit in memory on the 15.4 GB test host.** The weights alone are 18 GB. We predict Ollama refuses to load it, so `POST /tickets` returns **502** for 100% of requests. If it loads with swapping instead, single-request latency exceeds 120 s. Unless it runs on a host with 32 GB or more, it **cannot be measured**.
- **Q2. Qwen3.8 thinking (on by default) inflates S and Cs.** If thinking is not disabled, output grows from about 5 tokens to **300 to 1,500** (`ollama_eval_count` p50 > 300). At about 2 tokens/s that adds 2.5 to 12 minutes per ticket, and Cs² rises above 1. Reasoning text often mentions several categories, and `parse_category` picks the earliest one named, so accuracy drops by **5 to 10 points**.
- **T1 / C1. Tev1 and Clef Flash depend on the endpoint.** Through `/v1/systemone`, both always return a valid category, so `unclassified` is 0%. Through `/api/chat`, Tev1 replies in prose (as its library page states), and `unclassified` rises **above 10%**.
- **Cold start, all models.** The first request after an idle period of more than 5 minutes includes model loading (`ollama_load_duration_ns` > 0). That adds **5 to 15 s** for Tev1, **15 to 40 s** for Clef Flash, and more than 60 s for Qwen3.8.

## 4. Search predictions

- **S1.** At test-table size (≤ 3,000 rows), `GET /search` p95 is **< 100 ms** with no classification load running. It rises to **< 500 ms** while Ollama saturates the CPU, through scheduling contention only.
- **S2.** `GET /search` p95 exceeds **10 s** once more than 40 `POST /tickets` are in flight (B3). For Clef Flash at the surge rate of 334/h ([WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods)), this starts **15 to 20 min** into the run.

## 5. Categories expected to be hardest

1. **Bank account or service** (lowest recall for every model, below 65%). Our two annotators agreed on only 64% of golden tickets in this category, and one annotator put 31 tickets in Money transfer against 16 in the final set. Wire transfers, Zelle payments and frozen accounts sit on the boundary, and we expect models to send these tickets to Money transfer or service.
2. **Consumer loan** (recall below 70%). Auto loans, personal loans and lines of credit overlap with Credit card (revolving credit) and with Debt collection (a defaulted loan).
3. **Debt collection** (largest spread between models). With only 8 golden tickets, each error moves recall by 12.5 points. Collections that appear on credit reports are likely to be routed to Credit reporting.

Mortgage and Credit reporting are expected to be easiest (recall ≥ 85% for every model): both have distinctive vocabulary (escrow, servicer, foreclosure; bureau, dispute, inquiry), and annotators agreed on 100% and 84% of these tickets respectively.
