"""Build the fixed speed-test ticket list for the Assignment 2 S measurement.

The brief's load-test rate and run length both derive from S, the top model's
single-request service time. S is measured by sending three different tickets
of typical length to the model (after restart + warm-up) and taking the middle
timing. Each full run then sends about one request every 2*S seconds for S
minutes, which works out to around 30 tickets per run.

This script picks a fixed list, commits it to the repo, and sends the same
tickets in the same order for every configuration so that S and the per-run
load are comparable across models and runs.

Selection:
  - Source: rows 5000-5999 of data/ict3113_tickets.csv.
  - Excluded: all 150 golden rows (union of tuning_rows.csv and test_rows.csv).
  - Typical bucket: 30 non-golden rows whose narrative length is closest to
    800 chars (A1 typical ticket length; workload model median = 802, mean = 883).
  - Long bucket: 10 non-golden rows whose narrative length is closest to
    1770 chars (workload model p95 = 1772).
  - Ties broken by row number (lowest first), so the selection is deterministic.
  - Final list sorted by row ascending.

Writes:
  assignment2/speedtest/speedtest_rows.csv  (row, narrative_chars, bucket)

The first three rows of the typical bucket in sorted order are the "quick S"
tickets used for the S measurement itself.

Regenerate with:  python assignment2/speedtest/make_speedtest.py
"""

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE = os.path.join(ROOT, "data", "ict3113_tickets.csv")
SPLIT_DIR = os.path.join(ROOT, "assignment2", "split")
OUT_DIR = os.path.join(ROOT, "assignment2", "speedtest")

FIRST_ROW, LAST_ROW = 5000, 5999
TYPICAL_LEN, TYPICAL_N = 800, 30
LONG_LEN, LONG_N = 1770, 10


def load_golden_rows():
    rows = set()
    for name in ("tuning_rows.csv", "test_rows.csv"):
        path = os.path.join(SPLIT_DIR, name)
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                rows.add(int(r["row"]))
    return rows


def load_candidates(golden):
    out = []
    with open(SOURCE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row = int(r["row"])
            if row < FIRST_ROW or row > LAST_ROW:
                continue
            if row in golden:
                continue
            out.append((row, len(r["narrative"])))
    return out


def pick(candidates, target, n, taken):
    pool = [c for c in candidates if c[0] not in taken]
    pool.sort(key=lambda c: (abs(c[1] - target), c[0]))
    return [c[0] for c in pool[:n]]


def main():
    golden = load_golden_rows()
    if len(golden) != 150:
        sys.exit(f"expected 150 golden rows, loaded {len(golden)}")
    candidates = load_candidates(golden)
    expected = (LAST_ROW - FIRST_ROW + 1) - 150
    if len(candidates) != expected:
        sys.exit(f"expected {expected} non-golden candidates in [{FIRST_ROW},{LAST_ROW}], found {len(candidates)}")

    typical = set(pick(candidates, TYPICAL_LEN, TYPICAL_N, set()))
    long_ = set(pick(candidates, LONG_LEN, LONG_N, typical))

    by_row = {row: chars for row, chars in candidates}
    picks = sorted(
        [(row, by_row[row], "typical") for row in typical] +
        [(row, by_row[row], "long") for row in long_]
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    out_csv = os.path.join(OUT_DIR, "speedtest_rows.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "narrative_chars", "bucket"])
        w.writerows(picks)

    print(f"wrote {len(picks)} rows to {out_csv}")
    typical_rows = sorted(typical)
    print(f"  typical bucket ({len(typical_rows)} rows) target={TYPICAL_LEN} chars")
    print(f"  long bucket    ({len(long_)} rows) target={LONG_LEN} chars")
    print(f"  first 3 typical rows (quick-S tickets): {typical_rows[:3]}")


if __name__ == "__main__":
    main()
