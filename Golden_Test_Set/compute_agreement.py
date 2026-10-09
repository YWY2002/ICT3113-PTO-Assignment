"""Compute inter-annotator agreement for the golden test set.

Reads Owen's and Russell's independent labels from the two Annotator__*.xlsx
files in this folder and prints:
  - sample size
  - raw agreement (percentage of tickets where both annotators chose the same category)
  - Cohen's kappa (chance-corrected agreement)
  - a per-ticket disagreement list

Run from the repository root:  py -3.12 Golden_Test_Set/compute_agreement.py

Requires: openpyxl, scikit-learn (installed via requirements.txt).
"""

from pathlib import Path

import openpyxl
from sklearn.metrics import cohen_kappa_score

HERE = Path(__file__).parent
OWEN = HERE / "Annotator__Owen.xlsx"
RUSSELL = HERE / "Annotator__Russell.xlsx"
FINAL = HERE / "Final Golden Test Set.xlsx"


def load_labels(path):
    """Return {row_number: label} from the first sheet of the given xlsx.

    The `source_label` column holds the annotator's independent judgment
    (the column was originally the CFPB label but each annotator overwrote
    it with their own call).
    """
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            break
        out[int(row[0])] = row[1]
    return out


def main():
    owen = load_labels(OWEN)
    russell = load_labels(RUSSELL)
    final = load_labels(FINAL)

    common = sorted(set(owen) & set(russell))
    o = [owen[r] for r in common]
    r = [russell[r] for r in common]

    agree_count = sum(1 for a, b in zip(o, r) if a == b)
    raw_agreement = agree_count / len(common)
    kappa = cohen_kappa_score(o, r)

    print(f"Golden test set agreement (n = {len(common)})")
    print(f"  Raw agreement : {agree_count}/{len(common)} = {raw_agreement:.1%}")
    print(f"  Cohen's kappa : {kappa:.3f}")
    print()

    disagreements = [(row, owen[row], russell[row], final.get(row)) for row in common if owen[row] != russell[row]]
    print(f"Disagreements: {len(disagreements)}")
    print(f"{'row':>6}  {'Owen':<28}  {'Russell':<28}  Final")
    for row, o_lbl, r_lbl, f_lbl in disagreements:
        print(f"  {row:>4}  {o_lbl:<28}  {r_lbl:<28}  {f_lbl}")

    out_csv = HERE / "disagreements_resolved.csv"
    with open(out_csv, "w", encoding="utf-8", newline="\n") as f:
        f.write("row,owen_label,russell_label,final_label\n")
        for row, o_lbl, r_lbl, f_lbl in disagreements:
            f.write(f"{row},{o_lbl},{r_lbl},{f_lbl}\n")
    print(f"\nWrote {out_csv.name} ({len(disagreements)} rows)")


if __name__ == "__main__":
    main()
