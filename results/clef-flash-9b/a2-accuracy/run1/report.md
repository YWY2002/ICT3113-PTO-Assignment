# Test-set accuracy: clef-flash-9b

- Run folder: `results\clef-flash-9b\a2-accuracy\run1`
- Model: `clef-flash:9b`, digest `73e026ff389b28464bb26f8978f3164851a76832f0d339032747e2c56f98ea29`
- Endpoint: `systemone`
- Ollama: 0.40.16
- Test-set tickets: 75; found in service log: 75; HTTP errors or missing: 0; `unclassified`: 0
- Sender vs log category mismatches: 0

**Overall: 59/75 = 78.7%**

## Per category

| Category | Correct / n | Accuracy |
|---|---:|---:|
| Credit reporting | 18/19 | 94.7% |
| Debt collection | 2/4 | 50.0% |
| Mortgage | 8/9 | 88.9% |
| Credit card | 9/10 | 90.0% |
| Bank account or service | 12/21 | 57.1% |
| Consumer loan | 3/4 | 75.0% |
| Money transfer or service | 7/8 | 87.5% |

## Confusion matrix (rows: golden, columns: predicted)

| golden \ predicted | Credit reporting | Debt collection | Mortgage | Credit card | Bank account or service | Consumer loan | Money transfer or service | unclassified | (error) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Credit reporting | 18 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Debt collection | 1 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| Mortgage | 0 | 1 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| Credit card | 0 | 0 | 0 | 9 | 1 | 0 | 0 | 0 | 0 |
| Bank account or service | 0 | 0 | 0 | 2 | 12 | 0 | 7 | 0 | 0 |
| Consumer loan | 0 | 1 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| Money transfer or service | 0 | 0 | 0 | 1 | 0 | 0 | 7 | 0 | 0 |

## Single-request latency (no queueing; tickets sent one at a time)

Percentiles use the nearest-rank method. Not a speed-test result.

| | p50 | p95 | max |
|---|---:|---:|---:|
| Service `latency_ms` (s) | 9.00 | 12.88 | 13.96 |
