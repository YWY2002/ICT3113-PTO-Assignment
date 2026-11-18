"""Split the frozen golden set into a tuning set and a test set (Assignment 2, Step 1).

Rule (reading A, by position):
    Sort the 150 golden-set tickets by dataset row number (the `row` column,
    ascending). Counting from 1 in that sorted order, tickets in odd positions
    (1st, 3rd, ..., 149th) form the tuning set and tickets in even positions
    (2nd, 4th, ..., 150th) form the test set.

The tuning set is used only to design and adjust the cascade escalation rule.
The test set is used for every reported accuracy figure, including the limits.

Writes, next to this script:
    tuning_rows.csv   position, row, golden
    test_rows.csv     position, row, golden
    SPLIT.md          the rule, per-category counts, and both row lists

Usage (from the repository root):
    python assignment2/split/make_split.py
"""

import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLDEN = os.path.join(ROOT, "Golden_Test_Set", "Final Golden Test Set.xlsx")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

CATEGORIES = [
    "Credit reporting",
    "Debt collection",
    "Mortgage",
    "Credit card",
    "Bank account or service",
    "Consumer loan",
    "Money transfer or service",
]


def main():
    golden = pd.read_excel(GOLDEN)[["row", "source_label"]].rename(columns={"source_label": "golden"})
    if len(golden) != 150 or not golden.row.is_unique:
        raise SystemExit(f"expected 150 unique golden rows, found {len(golden)}")
    unknown = set(golden.golden) - set(CATEGORIES)
    if unknown:
        raise SystemExit(f"golden labels not in CATEGORIES: {unknown}")

    golden = golden.sort_values("row").reset_index(drop=True)
    golden.insert(0, "position", golden.index + 1)

    tuning = golden[golden.position % 2 == 1]
    test = golden[golden.position % 2 == 0]
    tuning.to_csv(os.path.join(OUT_DIR, "tuning_rows.csv"), index=False)
    test.to_csv(os.path.join(OUT_DIR, "test_rows.csv"), index=False)

    md = [
        "# Golden-set split (Assignment 2, Step 1)",
        "",
        "Committed before any Assignment 2 rule design or measurement.",
        "",
        "## Rule",
        "",
        "Sort the 150 golden-set tickets in `Golden_Test_Set/Final Golden Test Set.xlsx` "
        "by dataset row number (the `row` column, ascending). Counting from 1 in that sorted "
        "order, tickets in **odd positions** (1st, 3rd, ..., 149th) form the **tuning set** "
        "and tickets in **even positions** (2nd, 4th, ..., 150th) form the **test set**.",
        "",
        "This implements the brief's instruction \"Sort your golden-set tickets by row number. "
        "Odd rows are your tuning set. Even rows are your test set.\" with \"odd rows\" read as "
        "odd positions in the sorted list. The instruction to sort first only changes the "
        "result under this reading; with odd/even row *numbers*, order would not matter.",
        "",
        "- **Tuning set** (`tuning_rows.csv`): used only to design and adjust the cascade "
        "escalation rule and to choose its two settings.",
        "- **Test set** (`test_rows.csv`): used for every reported accuracy figure, including "
        "the overall and per-category limits derived from the top model.",
        "",
        "Regenerate with `python assignment2/split/make_split.py`.",
        "",
        "## Tickets per category",
        "",
        "| Category | Golden | Tuning | Test |",
        "|---|---:|---:|---:|",
    ]
    for c in CATEGORIES:
        md.append(
            f"| {c} | {(golden.golden == c).sum()} | {(tuning.golden == c).sum()} | {(test.golden == c).sum()} |"
        )
    md.append(f"| **Total** | **{len(golden)}** | **{len(tuning)}** | **{len(test)}** |")
    md += [
        "",
        "## Row numbers",
        "",
        f"**Tuning set ({len(tuning)}):** " + ", ".join(str(r) for r in tuning.row),
        "",
        f"**Test set ({len(test)}):** " + ", ".join(str(r) for r in test.row),
        "",
    ]
    with open(os.path.join(OUT_DIR, "SPLIT.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md))

    print(f"tuning: {len(tuning)} rows, test: {len(test)} rows -> {OUT_DIR}")


if __name__ == "__main__":
    main()
