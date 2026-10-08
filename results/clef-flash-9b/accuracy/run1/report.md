# Accuracy: clef-flash:9b

- Run folder: `results\clef-flash-9b\accuracy\run1`
- Model digest: `9f4115499b98bc31edb0337148ffa7fdf001b776f4f4795c9a22708c3396137a`
- Endpoint: `systemone`
- Golden tickets: 150; found in service log: 150; HTTP errors or missing: 0
- Sender vs log category mismatches: 0

## R4 verdict

| Check | Required | Measured | Pass |
|---|---|---|---|
| Overall accuracy | >= 120/150 (80%) | 120/150 = 80.0% (95% CI 72.9% to 85.6%) | yes |
| Recall >= 70% in every category | all 7 | 4/7 | no |
| `unclassified` | <= 3/150 (2%) | 0/150 | yes |
| **R4** | | | **FAIL** (borderline: overall within 3 points of 80%) |

## Per category

| Category | n | Correct | Recall | Needed | Pass | Predicted as | Precision |
|---|---:|---:|---:|---:|---|---:|---:|
| Credit reporting | 38 | 37 | 97% | 27 | yes | 40 | 92% |
| Debt collection | 8 | 5 | 62% | 6 | no | 14 | 36% |
| Mortgage | 19 | 17 | 89% | 14 | yes | 17 | 100% |
| Credit card | 16 | 14 | 88% | 12 | yes | 19 | 74% |
| Bank account or service | 39 | 23 | 59% | 28 | no | 25 | 92% |
| Consumer loan | 14 | 9 | 64% | 10 | no | 9 | 100% |
| Money transfer or service | 16 | 15 | 94% | 12 | yes | 26 | 58% |

## Confusion matrix (rows: golden, columns: predicted)

| golden \ predicted | Credit reporting | Debt collection | Mortgage | Credit card | Bank account or service | Consumer loan | Money transfer or service | unclassified | (error) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Credit reporting | 37 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Debt collection | 2 | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| Mortgage | 0 | 2 | 17 | 0 | 0 | 0 | 0 | 0 | 0 |
| Credit card | 1 | 0 | 0 | 14 | 1 | 0 | 0 | 0 | 0 |
| Bank account or service | 0 | 1 | 0 | 4 | 23 | 0 | 11 | 0 | 0 |
| Consumer loan | 0 | 5 | 0 | 0 | 0 | 9 | 0 | 0 | 0 |
| Money transfer or service | 0 | 0 | 0 | 1 | 0 | 0 | 15 | 0 | 0 |

## Most frequent confusions

| Golden | Predicted | Count |
|---|---|---:|
| Bank account or service | Money transfer or service | 11 |
| Consumer loan | Debt collection | 5 |
| Bank account or service | Credit card | 4 |
| Mortgage | Debt collection | 2 |
| Debt collection | Credit reporting | 2 |
| Bank account or service | Debt collection | 1 |
| Credit card | Bank account or service | 1 |
| Credit reporting | Debt collection | 1 |

## Single-request latency (no queueing; tickets sent one at a time)

Percentiles use the nearest-rank method.

| | p50 | p95 | p99 | mean | max |
|---|---:|---:|---:|---:|---:|
| Service `latency_ms` (s) | 9.49 | 13.23 | 14.49 | 9.73 | 15.48 |
| Output tokens | 0 | 0 | 0 | 0.0 | 0 |
