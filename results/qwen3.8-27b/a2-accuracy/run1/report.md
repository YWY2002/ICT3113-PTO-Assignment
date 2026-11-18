# Test-set accuracy: qwen3.8-27b

- Run folder: `results\qwen3.8-27b\a2-accuracy\run1`
- Model: `qwen3.8:27b`, digest `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`
- Endpoint: `chat`
- Ollama: 0.40.16
- Test-set tickets: 75; found in service log: 75; HTTP errors or missing: 0; `unclassified`: 0
- Sender vs log category mismatches: 0

**Overall: 61/75 = 81.3%**

## Per category

| Category | Correct / n | Accuracy |
|---|---:|---:|
| Credit reporting | 17/19 | 89.5% |
| Debt collection | 4/4 | 100.0% |
| Mortgage | 9/9 | 100.0% |
| Credit card | 8/10 | 80.0% |
| Bank account or service | 13/21 | 61.9% |
| Consumer loan | 4/4 | 100.0% |
| Money transfer or service | 6/8 | 75.0% |

## Confusion matrix (rows: golden, columns: predicted)

| golden \ predicted | Credit reporting | Debt collection | Mortgage | Credit card | Bank account or service | Consumer loan | Money transfer or service | unclassified | (error) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Credit reporting | 17 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Debt collection | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Mortgage | 0 | 0 | 9 | 0 | 0 | 0 | 0 | 0 | 0 |
| Credit card | 0 | 0 | 0 | 8 | 2 | 0 | 0 | 0 | 0 |
| Bank account or service | 0 | 0 | 0 | 0 | 13 | 0 | 8 | 0 | 0 |
| Consumer loan | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 |
| Money transfer or service | 0 | 0 | 0 | 0 | 2 | 0 | 6 | 0 | 0 |

## Single-request latency (no queueing; tickets sent one at a time)

Percentiles use the nearest-rank method. Not a speed-test result.

| | p50 | p95 | max |
|---|---:|---:|---:|
| Service `latency_ms` (s) | 39.55 | 85.65 | 96.70 |
