# Assignment 2 accuracy results (test set)

Written by `assignment2/accuracy/score_testset.py` from `results/*/a2-accuracy/run1/`.

## Limits

Top Assignment 1 model: `clef-flash:9b` (120/150 on the full golden set). On the test set: 59/75 = 78.7%.

- **Overall limit: 68.7%** (top model minus 10 points)
- Per-category limit: top model minus 15 points in each category

| Category | Test tickets | Top model | Limit | Note |
|---|---:|---:|---:|---|
| Credit reporting | 19 | 18/19 = 94.7% | 79.7% |  |
| Debt collection | 4 | 2/4 = 50.0% | 35.0% | too small for a fair test: one ticket = 25.0% |
| Mortgage | 9 | 8/9 = 88.9% | 73.9% | too small for a fair test: one ticket = 11.1% |
| Credit card | 10 | 9/10 = 90.0% | 75.0% |  |
| Bank account or service | 21 | 12/21 = 57.1% | 42.1% |  |
| Consumer loan | 4 | 3/4 = 75.0% | 60.0% | too small for a fair test: one ticket = 25.0% |
| Money transfer or service | 8 | 7/8 = 87.5% | 72.5% | too small for a fair test: one ticket = 12.5% |

## Configurations

Each category shows correct / n; `(below)` marks a category more than 15 points below the top model.

| Configuration | Overall | Credit reporting | Debt collection | Mortgage | Credit card | Bank account or service | Consumer loan | Money transfer or service | Overall limit | Category limits | Passes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| cascade-A | 60/75 = 80.0% | 18/19 | 2/4 | 9/9 | 9/10 | 12/21 | 3/4 | 7/8 | pass | pass | **yes** |
| cascade-B | 59/75 = 78.7% | 17/19 | 2/4 | 9/9 | 9/10 | 12/21 | 3/4 | 7/8 | pass | pass | **yes** |
| clef-flash-9b | 59/75 = 78.7% | 18/19 | 2/4 | 8/9 | 9/10 | 12/21 | 3/4 | 7/8 | pass | pass | **yes** |
| qwen3.8-27b | 61/75 = 81.3% | 17/19 | 4/4 | 9/9 | 8/10 | 13/21 | 4/4 | 6/8 | pass | pass | **yes** |
| tev1-4b | 60/75 = 80.0% | 18/19 | 2/4 | 9/9 | 9/10 | 12/21 | 3/4 | 7/8 | pass | pass | **yes** |

## Escalation

| Configuration | Escalated |
|---|---:|
| cascade-A | 17/75 = 22.7% |
| cascade-B | 36/75 = 48.0% |

## Comparison with Assignment 1

Each model's Assignment 1 accuracy run, scored on the same test rows. Not reused: every Assignment 2 figure above comes from the Assignment 2 run. Where the digest or Ollama version differs, a gap may come from that change.

| Configuration | Assignment 2 | Digest | Ollama | Assignment 1, test rows | Digest | Ollama |
|---|---:|---|---|---:|---|---|
| clef-flash-9b | 59/75 = 78.7% | `73e026ff389b` | 0.40.16 | 59/75 = 78.7% | `9f4115499b98` | 0.40.1 |
| qwen3.8-27b | 61/75 = 81.3% | `aaee06c39dcf` | 0.40.16 | 59/75 = 78.7% | `aaee06c39dcf` | 0.40.1 |
| tev1-4b | 60/75 = 80.0% | `7954dce22bc6` | 0.40.16 | 58/75 = 77.3% | `9b5bb969e46c` | 0.40.1 |
