# Accuracy: tev1:4b

- Run folder: `results\tev1-4b\accuracy\run1`
- Model digest: `9b5bb969e46c4b776826d6f2d401e22893205693f172653af6254897255025b8`
- Endpoint: `systemone`
- Golden tickets: 150; found in service log: 150; HTTP errors or missing: 1
- Sender vs log category mismatches: 0

## R4 verdict

| Check | Required | Measured | Pass |
|---|---|---|---|
| Overall accuracy | >= 120/150 (80%) | 119/150 = 79.3% (95% CI 72.2% to 85.0%) | no |
| Recall >= 70% in every category | all 7 | 4/7 | no |
| `unclassified` | <= 3/150 (2%) | 0/150 | yes |
| **R4** | | | **FAIL** (borderline: overall within 3 points of 80%) |

## Per category

| Category | n | Correct | Recall | Needed | Pass | Predicted as | Precision |
|---|---:|---:|---:|---:|---|---:|---:|
| Credit reporting | 38 | 37 | 97% | 27 | yes | 41 | 90% |
| Debt collection | 8 | 5 | 62% | 6 | no | 12 | 42% |
| Mortgage | 19 | 17 | 89% | 14 | yes | 18 | 94% |
| Credit card | 16 | 14 | 88% | 12 | yes | 18 | 78% |
| Bank account or service | 39 | 26 | 67% | 28 | no | 30 | 87% |
| Consumer loan | 14 | 6 | 43% | 10 | no | 6 | 100% |
| Money transfer or service | 16 | 14 | 88% | 12 | yes | 24 | 58% |

## Confusion matrix (rows: golden, columns: predicted)

| golden \ predicted | Credit reporting | Debt collection | Mortgage | Credit card | Bank account or service | Consumer loan | Money transfer or service | unclassified | (error) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Credit reporting | 37 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| Debt collection | 3 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Mortgage | 0 | 1 | 17 | 0 | 0 | 0 | 0 | 0 | 1 |
| Credit card | 1 | 0 | 0 | 14 | 1 | 0 | 0 | 0 | 0 |
| Bank account or service | 0 | 0 | 0 | 3 | 26 | 0 | 10 | 0 | 0 |
| Consumer loan | 0 | 6 | 1 | 0 | 1 | 6 | 0 | 0 | 0 |
| Money transfer or service | 0 | 0 | 0 | 0 | 2 | 0 | 14 | 0 | 0 |

## Most frequent confusions

| Golden | Predicted | Count |
|---|---|---:|
| Bank account or service | Money transfer or service | 10 |
| Consumer loan | Debt collection | 6 |
| Bank account or service | Credit card | 3 |
| Debt collection | Credit reporting | 3 |
| Money transfer or service | Bank account or service | 2 |
| Consumer loan | Bank account or service | 1 |
| Consumer loan | Mortgage | 1 |
| Credit card | Credit reporting | 1 |

## Single-request latency (no queueing; tickets sent one at a time)

Percentiles use the nearest-rank method.

| | p50 | p95 | p99 | mean | max |
|---|---:|---:|---:|---:|---:|
| Service `latency_ms` (s) | 6.38 | 17.74 | 31.13 | 8.31 | 32.55 |
| Output tokens | 1 | 1 | 1 | 1.0 | 1 |
