# Assignment 2 speed-test results

Written by `assignment2/speedtest/analyse_speed.py` from `results/*/a2-speed/run*/`.

- S = 8.89 s; offered rate 202.47 tickets/h; 9 min of arrivals, 6 min pause, 300 s HTTP timeout; 3 runs per configuration.
- Latency is JMeter's end-to-end time of completed requests (nearest-rank percentiles). Requests that timed out are counted as errors, not in the percentiles.

## Per configuration

| Configuration | Test-set accuracy | p50, mean of 3 runs (min-max) | p95, pooled (n) | Throughput (completed/h) | Errors + unfinished | Escalated |
|---|---:|---:|---:|---:|---:|---:|
| Tev1 4B | 60/75 = 80.0% | 5.6 s (5.0-6.5) | 11.9 s (90) | 212 | 0/90 = 0.0% | - |
| Cascade A | 60/75 = 80.0% | 6.8 s (6.6-7.1) | 20.1 s (90) | 201 | 0/90 = 0.0% | 13.3% |
| Clef Flash 9B (top model) | 59/75 = 78.7% | 12.6 s (10.3-15.2) | 29.7 s (89) | 207 | 1/90 = 1.1% | - |
| Cascade B | 59/75 = 78.7% | 9.7 s (8.7-10.6) | 27.5 s (90) | 203 | 0/90 = 0.0% | 40.0% |
| Qwen3.8 27B | 61/75 = 81.3% | 140.1 s (131.5-145.8) | 298.6 s (30) | 80 | 60/90 = 66.7% | - |

Speed relative to the top model (p50, mean of 3 runs; top model 12.6 s):

- Tev1 4B: 56% faster
- Cascade A: 46% faster
- Cascade B: 23% faster
- Qwen3.8 27B: 11.1 times slower

## Per run

| Configuration | Run | Sent | Completed | Errored | Unfinished | Errors | p50 (s) | Max (s) | Throughput (/h) | Stored by service | Escalated | Network (ms) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| Tev1 4B | run1 | 30 | 30 | 0 | 0 | - | 5.22 | 11.73 | 227 | 30 | - | 66 |
| Tev1 4B | run2 | 30 | 30 | 0 | 0 | - | 5.02 | 15.99 | 201 | 30 | - | 50 |
| Tev1 4B | run3 | 30 | 30 | 0 | 0 | - | 6.54 | 19.83 | 207 | 30 | - | 39 |
| Cascade A | run1 | 30 | 30 | 0 | 0 | - | 6.60 | 25.90 | 203 | 30 | 4/30 | 33 |
| Cascade A | run2 | 30 | 30 | 0 | 0 | - | 6.61 | 25.56 | 201 | 30 | 4/30 | 36 |
| Cascade A | run3 | 30 | 30 | 0 | 0 | - | 7.13 | 27.18 | 198 | 30 | 4/30 | 54 |
| Clef Flash 9B (top model) | run1 | 30 | 30 | 0 | 0 | - | 15.19 | 37.29 | 229 | 30 | - | 58 |
| Clef Flash 9B (top model) | run2 | 30 | 29 | 1 | 0 | connection error: 1 | 10.29 | 32.57 | 190 | 29 | - | 44 |
| Clef Flash 9B (top model) | run3 | 30 | 30 | 0 | 0 | - | 12.44 | 26.95 | 202 | 30 | - | 60 |
| Cascade B | run1 | 30 | 30 | 0 | 0 | - | 10.57 | 26.02 | 203 | 30 | 12/30 | 57 |
| Cascade B | run2 | 30 | 30 | 0 | 0 | - | 9.82 | 37.75 | 210 | 30 | 12/30 | 51 |
| Cascade B | run3 | 30 | 30 | 0 | 0 | - | 8.65 | 35.34 | 197 | 30 | 12/30 | 51 |
| Qwen3.8 27B | run1 | 30 | 11 | 19 | 0 | read timeout: 19 | 145.78 | 299.85 | 81 | 20 | - | 52 |
| Qwen3.8 27B | run2 | 30 | 10 | 20 | 0 | read timeout: 20 | 143.12 | 280.23 | 77 | 20 | - | 60 |
| Qwen3.8 27B | run3 | 30 | 9 | 21 | 0 | read timeout: 21 | 131.45 | 298.61 | 83 | 21 | - | 61 |

Stored by service = GET /stats after the run minus before. It can exceed Completed when the service finished a request after JMeter had given up on it.
