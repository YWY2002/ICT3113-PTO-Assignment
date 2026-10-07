"""Build the JMeter input files from the team's rows of the course dataset.

tickets.tsv       row <TAB> narrative, JSON-escaped so JMeter can paste it
                  straight into {"narrative": "..."}; no header line.
search_terms.txt  one query per line for GET /search.

Run from the repository root:  python loadtest/prepare_data.py
"""

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "data", "ict3113_tickets.csv")
OUT_DIR = os.path.join(ROOT, "loadtest")
FIRST_ROW, LAST_ROW = 5000, 5999

# Phrases an agent would type when checking for duplicates or similar cases.
SEARCH_TERMS = [
    "overdraft", "late fee", "dispute", "foreclosure", "escrow", "collector",
    "identity theft", "credit report", "wire transfer", "Zelle", "refund",
    "interest rate", "closed my account", "fraud", "loan modification",
    "charge off", "minimum payment", "inquiry", "debit card", "PayPal",
    "Equifax", "Experian", "TransUnion", "mortgage payment", "student loan",
    "car loan", "credit limit", "unauthorized", "harassment", "bankruptcy",
]


def main():
    with open(SOURCE, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if FIRST_ROW <= int(r["row"]) <= LAST_ROW]
    if len(rows) != LAST_ROW - FIRST_ROW + 1:
        raise SystemExit(f"expected {LAST_ROW - FIRST_ROW + 1} rows, found {len(rows)}")

    with open(os.path.join(OUT_DIR, "tickets.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            # json.dumps escapes quotes, backslashes, tabs and newlines, so each
            # narrative stays on one line with no raw tab; strip its outer quotes.
            f.write(f'{r["row"]}\t{json.dumps(r["narrative"])[1:-1]}\n')

    with open(os.path.join(OUT_DIR, "search_terms.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(SEARCH_TERMS) + "\n")

    print(f"wrote {len(rows)} tickets and {len(SEARCH_TERMS)} search terms to {OUT_DIR}")


if __name__ == "__main__":
    main()
