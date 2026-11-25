# Test-set accuracy: cascade-A

- Run folder: `results\cascade-A\a2-accuracy\run1`
- Model: `cascade-A`, digest `?`
- Endpoint: `cascade`
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

## Escalation

- Escalated: 17/75 = 22.7%
- Accuracy of escalated tickets: 9/17 = 52.9%
- Accuracy of non-escalated tickets: 51/58 = 87.9%

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
| Service `latency_ms` (s) | 5.36 | 17.21 | 20.40 |
