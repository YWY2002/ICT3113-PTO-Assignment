# Test-set accuracy: tev1-4b

- Run folder: `results\tev1-4b\a2-accuracy\run1`
- Model: `tev1:4b`, digest `7954dce22bc6c29c3b119656207681d12cb34434fed7caa086bfbc919bef0740`
- Endpoint: `systemone`
- Ollama: 0.40.16
- Test-set tickets: 75; found in service log: 75; HTTP errors or missing: 0; `unclassified`: 0
- Sender vs log category mismatches: 0

**Overall: 60/75 = 80.0%**

## Per category

| Category | Correct / n | Accuracy |
|---|---:|---:|
| Credit reporting | 18/19 | 94.7% |
| Debt collection | 2/4 | 50.0% |
| Mortgage | 9/9 | 100.0% |
| Credit card | 9/10 | 90.0% |
| Bank account or service | 12/21 | 57.1% |
| Consumer loan | 3/4 | 75.0% |
| Money transfer or service | 7/8 | 87.5% |

## Confusion matrix (rows: golden, columns: predicted)

| golden \ predicted | Credit reporting | Debt collection | Mortgage | Credit card | Bank account or service | Consumer loan | Money transfer or service | unclassified | (error) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Credit reporting | 18 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| Debt collection | 1 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| Mortgage | 0 | 0 | 9 | 0 | 0 | 0 | 0 | 0 | 0 |
| Credit card | 0 | 0 | 0 | 9 | 1 | 0 | 0 | 0 | 0 |
| Bank account or service | 0 | 0 | 0 | 2 | 12 | 0 | 7 | 0 | 0 |
| Consumer loan | 0 | 1 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| Money transfer or service | 0 | 0 | 0 | 0 | 1 | 0 | 7 | 0 | 0 |

## Single-request latency (no queueing; tickets sent one at a time)

Percentiles use the nearest-rank method. Not a speed-test result.

| | p50 | p95 | max |
|---|---:|---:|---:|
| Service `latency_ms` (s) | 4.91 | 7.39 | 8.37 |
