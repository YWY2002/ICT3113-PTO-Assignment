# Accuracy: qwen3.8:27b

- Run folder: `results\qwen3.8-27b\accuracy\run1`
- Model digest: `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`
- Endpoint: `chat`
- Golden tickets: 150; found in service log: 150; HTTP errors or missing: 0
- Sender vs log category mismatches: 0

## R4 verdict

| Check | Required | Measured | Pass |
|---|---|---|---|
| Overall accuracy | >= 120/150 (80%) | 119/150 = 79.3% (95% CI 72.2% to 85.0%) | no |
| Recall >= 70% in every category | all 7 | 6/7 | no |
| `unclassified` | <= 3/150 (2%) | 0/150 | yes |
| **R4** | | | **FAIL** (borderline: overall within 3 points of 80%) |

## Per category

| Category | n | Correct | Recall | Needed | Pass | Predicted as | Precision |
|---|---:|---:|---:|---:|---|---:|---:|
| Credit reporting | 38 | 30 | 79% | 27 | yes | 32 | 94% |
| Debt collection | 8 | 7 | 88% | 6 | yes | 17 | 41% |
| Mortgage | 19 | 18 | 95% | 14 | yes | 19 | 95% |
| Credit card | 16 | 13 | 81% | 12 | yes | 15 | 87% |
| Bank account or service | 39 | 27 | 69% | 28 | no | 32 | 84% |
| Consumer loan | 14 | 11 | 79% | 10 | yes | 12 | 92% |
| Money transfer or service | 16 | 13 | 81% | 12 | yes | 23 | 57% |

## Confusion matrix (rows: golden, columns: predicted)

| golden \ predicted | Credit reporting | Debt collection | Mortgage | Credit card | Bank account or service | Consumer loan | Money transfer or service | unclassified | (error) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Credit reporting | 30 | 6 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Debt collection | 1 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Mortgage | 0 | 0 | 18 | 0 | 0 | 1 | 0 | 0 | 0 |
| Credit card | 1 | 0 | 0 | 13 | 2 | 0 | 0 | 0 | 0 |
| Bank account or service | 0 | 1 | 0 | 1 | 27 | 0 | 10 | 0 | 0 |
| Consumer loan | 0 | 3 | 0 | 0 | 0 | 11 | 0 | 0 | 0 |
| Money transfer or service | 0 | 0 | 0 | 0 | 3 | 0 | 13 | 0 | 0 |

## Most frequent confusions

| Golden | Predicted | Count |
|---|---|---:|
| Bank account or service | Money transfer or service | 10 |
| Credit reporting | Debt collection | 6 |
| Money transfer or service | Bank account or service | 3 |
| Consumer loan | Debt collection | 3 |
| Credit card | Bank account or service | 2 |
| Bank account or service | Debt collection | 1 |
| Bank account or service | Credit card | 1 |
| Credit card | Credit reporting | 1 |

## Single-request latency (no queueing; tickets sent one at a time)

Percentiles use the nearest-rank method.

| | p50 | p95 | p99 | mean | max |
|---|---:|---:|---:|---:|---:|
| Service `latency_ms` (s) | 41.54 | 98.61 | 116.93 | 46.92 | 129.13 |
| Output tokens | 202 | 532 | 628 | 243.4 | 715 |
