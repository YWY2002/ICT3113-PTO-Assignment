# Performance and Accuracy Requirements

Every requirement below is derived from the [workload model](../WorkloadModel/workload_model.md), cited as WM §n with a link to the section each figure comes from. The derivation follows this chain: business driver → arrival rate × service demand → utilisation → capacity decision.

## 1. Candidate models

| Model | Ollama tag | Size class | Download | Digest |
|---|---|---|---:|---|
| Tev1 4B | `tev1:4b` | Small (≤ 5B) | 4.5 GB | `TODO: from /api/tags or the service startup log` |
| Clef Flash 9B | `clef-flash:9b` | Medium (5B to 15B) | 11 to 12 GB | `TODO` |
| Qwen3.8 27B | `qwen3.8:27b` | Large (> 15B) | 18 GB | `TODO` |

The three models span three size classes and make the speed-accuracy trade-off visible. The two smaller models are fine-tuned for classification and routing, while Qwen3.8 27B is a general-purpose model with thinking turned on by default:

- Tev1 4B is fine-tuned from Qwen3.5-4B for classification, including banking and ticket-routing data.
- Clef Flash 9B is fine-tuned from Qwen3.5-9B. It scores every option in a single forward pass instead of generating text.
- Qwen3.8 27B is a general-purpose model with thinking on by default.

The set asks whether a small specialised model can match a large general one under the client's CPU-only constraint.

**Integration note.** The Ollama library pages state that `tev1` and `clef-flash` are served through `/v1/systemone`, not `/api/chat`; in plain chat, Tev1 replies in prose. The baseline calls `/api/chat`, so the team must settle how these two models are called before the first benchmark run.

## 2. System model used for the derivations

- **Transaction types.** There are two. `POST /tickets` visits the model backend once (V = 1). `GET /search` is a SQLite `LIKE` scan and never visits Ollama.
- **Bottleneck.** Ollama inference has by far the largest demand. SQLite and FastAPI take milliseconds against seconds for inference, so the service is modelled as a single-server queue with D_ollama = S (service demand law).
- **Ceiling.** X ≤ 1 / S, and the practical ceiling is 0.7 / S under the 70% planning rule.
- **Variability.** JMeter's open-model arrivals are Poisson, so Ca² = 1. Service time scales with prompt tokens, and ticket-length CV is **0.53** ([WM §4](../WorkloadModel/workload_model.md#4-ticket-length)). Adding the fixed 274-character prompt to the mean ticket of 883 characters (same section) lowers the CV of request size to 464.8 / (883 + 274) = 0.40, so Cs² is low, about 0.05 to 0.16. Kingman gives:
  W ≈ ρ/(1−ρ) × (Ca² + Cs²)/2 × S

### Arrival rates the requirements must hold under (Expected scenario)

| Condition | Tickets/h | λ (tickets/s) | Interarrival | Source |
|---|---:|---:|---:|---|
| Average | 49 | 0.0136 | 73 s | [WM §1](../WorkloadModel/workload_model.md#1-ticket-volume) (`tickets_per_hour` = 49.12) |
| Peak hour | 167 | 0.0464 | 21.6 s | [WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods) (`peak_rate`, `arrival_rate_per_second`, `interarrival_time`) |
| Peak hour, p99 (Poisson) | 198 | 0.0550 | 18.2 s | [WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods) (`peak_p99`) |
| Surge (peak × 2) | 334 | 0.0928 | 10.8 s | [WM §2](../WorkloadModel/workload_model.md#peak-and-surge-per-second) (`surge_rate`) |

Tickets/h for every row, and λ and interarrival for the peak and surge rows, are taken directly from the workload model. For the average and p99 rows, λ = tickets/h ÷ 3,600 and interarrival = 1 / λ, derived here.

### What these rates allow for S

| Condition | Largest S at ρ ≤ 0.7 | Largest S for a stable queue (ρ < 1) |
|---|---:|---:|
| Peak hour, 167/h | 15.1 s | 21.6 s |
| Peak p99, 198/h | 12.7 s | 18.2 s |
| Surge, 334/h | **7.5 s** | **10.8 s** |

The surge is the binding constraint. A model whose mean S is about 10 s handles the peak hour comfortably but cannot keep up with a surge.

## 3. Requirements

All load tests use JMeter open-loop arrivals (Open Model Thread Group or Precise Throughput Timer) with narratives drawn from rows 5000 to 5999. Each configuration is run three times. Latency is measured end to end at JMeter and reconciled with `latency_ms` in the service log.

### R1. Throughput: sustain the surge

**Statement.** At an offered open-loop rate of **334 tickets/h** for **60 min**, all of the following must hold:
- achieved `POST /tickets` throughput is **≥ 98%** of offered (≥ 327 tickets/h),
- error rate is **< 1%**,
- latency is not growing: p95 in the last 15 min is **≤ 1.5×** the p95 in the first 15 min.

**Justification.**
- Surge = peak × surge factor 2 = 167 × 2 = 334 tickets/h ([WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods), `surge_factor`, `surge_rate`). That factor comes from the 1.74 to 2.30 event excess measured across the 10 peer banks (same section, `event_excess`).
- Under the Utilisation Law (U = X × S < 1), a model can sustain 334/h only if mean S < 10.8 s. To keep ρ ≤ 0.7 headroom, S must be ≤ 7.5 s, which is a capacity of at least 477 tickets/h.
- Below that, the queue grows by (λ − 1/S) tickets per hour and latency grows without bound.

**Position.** Requirements are set on the Expected scenario. The Maximum scenario (670/h surge, [WM §2](../WorkloadModel/workload_model.md#tickets-per-hour)) is the stress-test target, not a requirement, because at Maximum volume the client would need several servers (X ≤ c / S) and A1 tests a single server.

### R2. Response time: `POST /tickets` at peak

**Statement.** At an offered open-loop rate of **198 tickets/h** for **60 min**:
- `POST /tickets` latency **p95 ≤ 10 s** and **p99 ≤ 20 s**,
- error rate **< 1%**.

**Justification.**
- 198/h is the 99th-percentile hourly count at peak ([WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods), `peak_p99`), so the requirement holds in 99% of peak hours, not just the average one.
- 10 s is the limit beyond which attention is hard to hold (Miller 1968; Nielsen 1993;). The intake form waits synchronously for the category.
- Percentiles rather than means, because latency distributions are right-skewed.
- By Kingman, R2 holds only if mean S is about 6 s or less: at S = 5 s, ρ = 0.28 and mean R ≈ 6.1 s.

### R3. Response time: `GET /search` under mixed load

**Statement.** At **800 searches/h** offered open-loop, together with **198 `POST /tickets`/h**, for **60 min**:
- `GET /search` latency **p95 ≤ 1 s**,
- error rate **< 1%**.

**Justification.**
- 798 searches/h is the upper search rate in the busiest month ([WM §3](../WorkloadModel/workload_model.md#3-agent-search-rate), `searches_per_hour_peak_month` at 3 searches per ticket), rounded up to 800. An agent is waiting on screen, so the 1 s "flow of thought kept" threshold applies.
- Search shares the host CPU and FastAPI's 40-thread pool with ticket classification. Mixed load is therefore the condition that matters.

**Limitation.** The service starts empty, so during testing the table holds at most a few thousand rows. In production it would grow by about 430,000 tickets a year ([WM §1](../WorkloadModel/workload_model.md#1-ticket-volume), `expected_tickets_per_year`), and `LIKE '%q%'` scans the whole table. R3 is verified only at test-table size, and its validity at production size is stated as a risk.

### R4. Classification accuracy

**Statement.** Measured by sending all 150 golden-set tickets through `POST /tickets`, scored against the golden labels:

- **Overall accuracy ≥ 80%**, which is at least 120/150 correct.
- **Recall ≥ 70% in every category**, stated as counts because the categories are small:

  | Category | Golden tickets | Must be correct |
  |---|---:|---:|
  | Bank account or service | 39 | ≥ 28 |
  | Credit reporting | 38 | ≥ 27 |
  | Mortgage | 19 | ≥ 14 |
  | Money transfer or service | 16 | ≥ 12 |
  | Credit card | 16 | ≥ 12 |
  | Consumer loan | 14 | ≥ 10 |
  | Debt collection | 8 | ≥ 6 |

- **`unclassified` ≤ 2%**, which is at most 3/150.

**Justification.**
- **Floor.** Consumer-selected labels agree with the golden labels on only 68% of the golden set. That is what routing on the raw label would achieve, so a model below it adds nothing.
- **Ceiling.** The two independent annotators agreed on 84.7% of tickets. That is approximately what a human reader achieves, and no requirement above it is credible.
- **Staffing cost.** At the Expected 430,257 tickets/yr ([WM §1](../WorkloadModel/workload_model.md#1-ticket-volume), `expected_tickets_per_year`), each percentage point of accuracy is about 12 misrouted tickets a day. Misrouted tickets per day are 377 at 68%, 236 at 80% and 177 at 85%.
- **Per-category recall.** Without it, a model could pass overall while consistently misrouting a small category.

**Position.** A triage delay of seconds is invisible next to complaint-handling times of hours or days, while every misroute costs an agent a transfer. **Accuracy takes priority over latency.** R1 and R2 only require the service to keep up with demand.

**Measurement uncertainty.** With n = 150, a measured 80% has a 95% Wilson interval of 73% to 86%. A model measured within about 3 points of the threshold is reported as borderline, not as a clear pass or fail.

## 4. Test validity conditions

- **Sample size.** A 60-min run at 198/h ([WM §2](../WorkloadModel/workload_model.md#2-peak-and-non-peak-periods)) yields about 200 requests, so p99 rests on about 2 samples. p99 is reported over all three runs pooled (about 600 samples), and per-run spread is shown for p50 and p95.
- **Warm-up.** Ollama unloads an idle model after 5 min by default. Each run starts with one discarded warm-up request so that model loading is not counted as service time. Cold-start time is reported separately from `ollama_load_duration_ns`.
- **Separate load generator.** JMeter runs on a separate machine from the service and Ollama, as the brief requires.
