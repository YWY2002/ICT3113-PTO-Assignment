# Prediction Record

Predictions are stated so they can be shown wrong by the service logs (`logs/*.jsonl`) and the JMeter `.jtl` files.

Workload figures come from the [workload model](../WorkloadModel/workload_model.md), cited as WM §n with a link to the section. Requirement IDs (R1 to R4) refer to [Requirements.md](Requirements.md).

**Assumed system under test** Ollama and the triage service run on an Intel Core i9-13900KF, 64 GB RAM, dual-channel DDR5 at 4800 MT/s, Windows 11 Pro, CPU only.

## System Hardware Specifications
- Intel Core i9-13900KF (13th gen, Raptor Lake)
  - 24 cores / 32 threads: 8 performance cores (2 threads each) and 16 efficiency cores
  - 3.0 GHz base speed (performance cores), 2.2 GHz base speed (efficiency cores)
  - Supports AVX2 and AVX-VNNI, but not AVX-512
  - No integrated graphics (KF model)
- RAM
  - Total installed 2 x 32 GB (63.8 GB usable)
  - DDR5, rated 6400 MT/s but configured at 4800 MT/s (XMP off). It must stay at 4800 MT/s for every run.
- GPU
  - NVIDIA GeForce RTX 4070. Not used: Ollama is started with `CUDA_VISIBLE_DEVICES=-1`, `OLLAMA_VULKAN=0` and `GGML_VK_VISIBLE_DEVICES=-1`, which hide the GPU from both the CUDA and the Vulkan backends, so inference runs on the CPU only (A1).
- Windows 11 Pro, Ollama 0.40.1, Docker 29.8.0, Python 3.13.1

## 1. How the latency predictions were made

Service time is estimated with an execution model:

S ≈ prompt tokens / prefill rate + output tokens / decode rate + fixed overhead

- **Prompt tokens.** These are (ticket characters + instruction characters) / 4, using 4 characters per token ([WM §4](../WorkloadModel/workload_model.md#4-ticket-length), `characters_per_token`). Ticket lengths are the median of 802 characters, the mean of 883 and the p95 of 1,772 (same section).
  - `/api/chat` path (Qwen3.8): 274 instruction characters ([WM §4](../WorkloadModel/workload_model.md#4-ticket-length), `prompt_characters`) plus chat template. That is about 284 tokens at the median ticket and about 510 at p95.
  - `/v1/systemone` path (Tev1, Clef Flash): the ticket is sent as `state` with one `choice` question (`SYSTEMONE_QUESTION` in `app/main.py`): a 94-character instruction and the seven category names as options, about 420 characters as JSON. This is the same information as `SYSTEM_PROMPT`, but the endpoint wraps the request in its own template. The Clef Flash library page reports 486 input tokens for a 65-character state with three short questions, so we assume about **300 tokens** of template and question per request on top of the ticket. That is about 500 tokens at the median ticket and about 740 at p95. The service logs the real count (`ollama_prompt_eval_count`), so this assumption is tested directly.
- **Prefill rate.** Prefill is compute-bound: about 2 × parameters FLOPs per token. Rates are scaled from an earlier estimate for an 8-core Zen 2 laptop CPU (70, 30 and 10 tokens/s) by the ratio of peak FP32 throughput at base clock:
  - Zen 2 reference: 8 cores × 32 FLOPs/cycle × 2.9 GHz = 742 GFLOPS.
  - i9-13900KF: 8 performance cores × 32 FLOPs/cycle × 3.0 GHz + 16 efficiency cores × 16 FLOPs/cycle × 2.2 GHz = 768 + 563 = 1,331 GFLOPS.
  - Ratio 1,331 / 742 = 1.79, so the estimated rates are **125 tokens/s for 4B, 54 for 9B and 18 for 27B**.
- **Decode rate.** Decode is memory-bandwidth-bound: effective bandwidth divided by model size. Dual-channel DDR5 at 4800 MT/s has a peak of 76.8 GB/s; at the same 68% efficiency assumed for the earlier estimate (35 of 51.2 GB/s), that is about 52.5 GB/s effective, so about **2.9 tokens/s** for the 18 GB Qwen3.8. Tev1 and Clef Flash score options in a single pass, so they have no decode phase.
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

**B4. The network between JMeter and the service is not the bottleneck.** JMeter runs on a different machine on a different network and reaches the service over the internet (A3). For every request, the gap between JMeter's elapsed time and the service's `latency_ms` (matched by `req_id` / `request_id`) has a median **≤ 150 ms** and p99 **≤ 500 ms**, which is under 4% of Tev1's median service time (4.3 s). Connection errors (no HTTP status) stay **below 0.5%** of requests.

**Why.** Inference demand (seconds) exceeds every other demand, including the network round trip (tens of milliseconds), by two to three orders of magnitude, so by bottleneck analysis Ollama saturates first.

## 3. Per-model predictions

| | `tev1:4b` | `clef-flash:9b` | `qwen3.8:27b` |
|---|---:|---:|---:|
| **Overall accuracy on golden set** | **72%** (108/150) | **78%** (117/150) | **83%** (125/150) |
| `unclassified` rate | ≤ 2% | ≤ 2% | 5% to 15% with thinking on |
| **Single-request latency, p50** | **4.3 s** | **9.6 s** | **120 s** with thinking on (Q2); 17.8 s with thinking off |
| Single-request latency, p95 | 6.2 s | 14.0 s | 547 s with thinking on; 31.2 s with thinking off |
| Single-request latency, p99 | 6.6 s | 14.8 s | 549 s with thinking on; 33.4 s with thinking off |
| Throughput ceiling (3600 / mean S) | about 805 tickets/h | about 360 tickets/h | about 11 tickets/h with thinking on; about 190 with thinking off |
| R1 (surge 334/h, [WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods)) | **Pass**: ρ ≈ 0.41, mean R ≈ 6.1 s | **Fail, borderline**: ρ ≈ 0.92, mean R ≈ 73 s; throughput keeps up, but queue swings break the 1.5× p95 growth limit | **Fail**: ρ ≈ 30; thread pool full from about 7 min; 502s from about 10 min |
| R2 (p95 ≤ 10 s at 198/h, [WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods)) | **Pass**: ρ ≈ 0.25, mean R ≈ 5.2 s, p95 ≈ 7 to 9 s | **Fail**: ρ ≈ 0.55, mean R ≈ 16 s; p95 service time alone is 14 s | **Fail**: ρ ≈ 18; thread pool full from about 13 min |
| R4 (≥ 80% overall) | **Fail** | **Borderline fail** | **Pass** |

Latency p50, p95 and p99 use the median (802), p95 (1,772) and p99 (1,930) ticket lengths, and the throughput ceiling uses the mean (883), all from [WM §4](../WorkloadModel/workload_model.md#4-ticket-length). For Qwen3.8 with thinking on, p50 assumes 300 output tokens, p95 and p99 assume 1,500, and the mean assumes 900 (the range in Q2). Single-request latency is measured with one request in the system at a time (the accuracy runs), so it contains no queueing. Because service time grows only with prompt length and ticket length is capped at 2,000 characters, we predict p99 is **within 10%** of p95 for Tev1 and Clef Flash; a larger gap means something other than prompt length (cold starts, CPU contention, long outputs) is driving the tail. R1 and R2 queueing figures apply Kingman at the arrival rates in [WM §2](../WorkloadModel/workload_model.md#tickets-per-hour).

Accuracy reasoning:
- **Tev1 4B.** Its published mean accuracy across 13 human-labelled datasets is 73.3%, and it was trained on banking data. We expect about the same here.
- **Clef Flash 9B.** A larger model of the same family as Tev1, so we expect higher accuracy.
- **Qwen3.8 27B.** The largest model, but capped by the 84.7% human agreement on this set.

**Model-specific predictions:**

- **Q1. Qwen3.8 27B fits in memory on the 63.8 GB test host.** The weights are 18 GB, so Ollama loads it fully into RAM and `ollama ps` shows 100% CPU. It is therefore measured, but it is far slower than the other two candidates (Q2).
- **Q2. Qwen3.8 thinking (on by default) inflates S and Cs.** If thinking is not disabled, output grows from about 5 tokens to **300 to 1,500** (`ollama_eval_count` p50 > 300). At about 2.9 tokens/s that adds 1.7 to 8.6 minutes per ticket, and Cs² rises above 1. Tickets that generate more than about 1,650 output tokens pass the 600 s `OLLAMA_TIMEOUT` and return **502**, so even the one-at-a-time accuracy run will show some errors. Reasoning text often mentions several categories, and `parse_category` picks the earliest one named, so accuracy drops by **5 to 10 points**.
- **T1 / C1. Tev1 and Clef Flash depend on the endpoint.** Through `/v1/systemone`, both always return a valid category, so `unclassified` is 0%. Through `/api/chat`, Tev1 replies in prose (as its library page states), and `unclassified` rises **above 10%**.
- **Cold start, all models.** The first request after an idle period of more than 5 minutes includes model loading (`ollama_load_duration_ns` > 0). That adds **5 to 15 s** for Tev1, **15 to 40 s** for Clef Flash, and more than 60 s for Qwen3.8.

## 4. Search predictions

- **S1.** At test-table size (≤ 3,000 rows), `GET /search` server-side `latency_ms` p95 is **< 100 ms** with no classification load running. It rises to **< 500 ms** while Ollama saturates the CPU, through scheduling contention only. Measured at JMeter, each value is higher by the network round trip (B4), so the JMeter p95 is **< 600 ms** under load and R3 (p95 ≤ 1 s) holds while the thread pool is not exhausted.
- **S2.** `GET /search` p95 exceeds **10 s** once more than 40 `POST /tickets` are in flight (B3). This happens only for Qwen3.8, about **13 min** into a mixed run at 198/h and about **7 min** into a surge run at 334/h ([WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods)). Tev1 and Clef Flash never reach 40 in flight.

## 5. Categories expected to be hardest

1. **Bank account or service** (lowest recall for every model, below 65%). Our two annotators agreed on only 64% of golden tickets in this category, and one annotator put 31 tickets in Money transfer against 16 in the final set. Wire transfers, Zelle payments and frozen accounts sit on the boundary, and we expect models to send these tickets to Money transfer or service.
2. **Consumer loan** (recall below 70%). Auto loans, personal loans and lines of credit overlap with Credit card (revolving credit) and with Debt collection (a defaulted loan).
3. **Debt collection** (largest spread between models). With only 8 golden tickets, each error moves recall by 12.5 points. Collections that appear on credit reports are likely to be routed to Credit reporting.

Mortgage and Credit reporting are expected to be easiest (recall ≥ 85% for every model): both have distinctive vocabulary (escrow, servicer, foreclosure; bureau, dispute, inquiry), and annotators agreed on 100% and 84% of these tickets respectively.

## 6. Assumptions

Every prediction above rests on these assumptions. Where a result contradicts a prediction, the first step is to check which assumption failed.

**Test environment**
- A1. Ollama 0.40.1 runs natively on the i9-13900KF (Windows 11 Pro), CPU only. The RTX 4070 is hidden from Ollama's CUDA backend with `CUDA_VISIBLE_DEVICES=-1` and from its Vulkan backend with `OLLAMA_VULKAN=0` and `GGML_VK_VISIBLE_DEVICES=-1`, so there is no GPU offload (`ollama ps` shows 100% CPU). Hiding CUDA alone is not enough: Ollama 0.40.1 then finds the GPU through Vulkan.
- A2. Ollama serves one request at a time per model (`OLLAMA_NUM_PARALLEL=1`), so the model backend behaves as a single server.
- A3. JMeter runs on a separate machine on a **different network**, reaching the service over the internet (through port forwarding or a tunnel to port 8000). Network round-trip time is tens of milliseconds with some jitter: small next to service times of seconds, but visible in `GET /search` latency. The connection path does not time out or drop requests that take up to 650 s (JMeter's response timeout), so slow requests fail only through the service's own 600 s limit.
- A4. Each run starts with an empty database and a discarded warm-up request, so cold-start model loading is excluded from measured service times. Ollama's default 5-minute keep-alive keeps the model loaded during a run.
- A5. Thermal throttling under sustained all-core load and background processes do not change service time by more than 10% across a 60-minute run.

**Service time (execution model, section 1)**
- A6. English text averages 4 characters per token ([WM §4](../WorkloadModel/workload_model.md#4-ticket-length)). The candidates' own tokenizers may differ.
- A7. The `/api/chat` template adds about 15 tokens; the `/v1/systemone` template plus our question adds about 300 tokens, inferred from the 486-token example on the Clef Flash library page.
- A8. Prefill runs at about 125 tokens/s (4B), 54 (9B) and 18 (27B): an 8-core Zen 2 estimate scaled by the 1.79 ratio of peak FP32 throughput at base clock (section 1). This assumes Ollama uses both the performance and the efficiency cores; if it uses only the performance cores, prefill is slower, by up to about 40%.
- A9. Decode runs at about 52.5 GB/s effective memory bandwidth divided by model size (about 2.9 tokens/s for the 18 GB Qwen3.8). RAM stays at 4800 MT/s for every run.
- A10. Tev1 and Clef Flash score all options in a single forward pass with no token-by-token decoding, as their library pages state.
- A11. HTTP, JSON and SQLite add about 0.3 s per request.
- A12. Model sizes (4.5 GB, 11 to 12 GB, 18 GB) are the download sizes on the Ollama library pages. Quantisation is not published, so memory use is assumed to be about the download size.

**Queueing (sections 2 and 3)**
- A13. JMeter `random_arrivals` produce Poisson arrivals, so Ca² = 1.
- A14. Service time scales with prompt length, so Cs² follows from ticket-length variability: about 0.05 for Tev1 and Clef Flash, about 0.12 for Qwen3.8 with thinking off.
- A15. Kingman's G/G/1 approximation applies, because Ollama is a single server (A2) fed by independent arrivals.

**Model behaviour**
- A16. The baseline sends no `think` parameter, so Qwen3.8 thinks by default (its library page states thinking is on by default).
- A17. All three models fit in RAM (18 GB at most on 63.8 GB), so none runs from swap.
- A18. Tev1's published 73.3% mean accuracy across 13 human-labelled datasets transfers to our seven-category task; Clef Flash, a larger model of the same family, scores higher.
- A19. The 84.7% agreement between our two annotators approximates the best accuracy any model can show against our golden labels, and the golden labels themselves are correct.

**Search (section 4)**
- A20. The test database holds at most about 3,000 tickets, so a `LIKE` scan takes milliseconds.
