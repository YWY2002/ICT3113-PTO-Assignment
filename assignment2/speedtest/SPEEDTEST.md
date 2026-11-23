# Speed-test ticket list (Assignment 2)

The Assignment 2 load-test rate and run length both derive from S, the top
model's single-request service time. This list is the fixed set of tickets
used to measure S and to drive the load runs that follow. The same list, in
the same order, is used for every configuration so S and the per-run load are
comparable across models and runs.

## Selection rule

- Source: rows 5000-5999 of `data/ict3113_tickets.csv`.
- Excluded: all 150 golden rows (union of
  `assignment2/split/tuning_rows.csv` and `assignment2/split/test_rows.csv`).
- Typical bucket: 30 non-golden rows whose narrative length is closest to
  **800 characters** (A1 typical ticket length; workload model median 802,
  mean 883).
- Long bucket: 10 non-golden rows whose narrative length is closest to
  **1,770 characters** (workload model p95 1,772).
- Ties broken by row number (lowest first), so the selection is deterministic.
- Final list sorted by row ascending in `speedtest_rows.csv`.

Regenerate with `python assignment2/speedtest/make_speedtest.py`.

## Quick-S measurement

After `sut_prepare.ps1` has started a fresh service and sent its three fixed
warm-up tickets, send the first three rows of the typical bucket to the
top-model-alone configuration, one at a time, and take the middle timing as
**S**:

| # | Row | Narrative chars |
|---:|---:|---:|
| 1 | 5009 | 817 |
| 2 | 5026 | 813 |
| 3 | 5093 | 821 |

## Full speed-test list (40 rows)

30 typical + 10 long. Listed in row order.

**Typical (30):** 5009, 5026, 5093, 5110, 5131, 5146, 5171, 5225, 5353, 5391,
5394, 5396, 5402, 5422, 5446, 5455, 5585, 5596, 5605, 5625, 5683, 5703, 5717,
5788, 5864, 5869, 5981, 5982, 5992, 5996

**Long (10):** 5042, 5149, 5331, 5414, 5486, 5489, 5552, 5613, 5695, 5860
