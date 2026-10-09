# Golden Test Set — Inter-Annotator Agreement

The brief requires an inter-annotator agreement statistic and a record of
every disagreement resolution. Both are produced by
[`compute_agreement.py`](compute_agreement.py), which reads the two
independent annotator sheets and the final frozen set.

## How to reproduce

```powershell
py -3.12 -m pip install openpyxl scikit-learn
py -3.12 Golden_Test_Set/compute_agreement.py
```

## Result (n = 150)

| Statistic | Value |
|---|---:|
| Raw agreement | 127/150 = **84.7%** |
| Cohen's κ | **0.817** (near-perfect per Landis & Koch) |
| Disagreements | **23** |

The κ is above 0.8, which is the "almost perfect" band in the Landis & Koch
convention. The 84.7% raw agreement is the empirical ceiling for any model
scored against our golden labels: no classifier can exceed what two careful
humans agree on, and the labels themselves are only as reliable as that
agreement.

## Where the independent labels live

Both annotators labelled the same 150 tickets independently. Each wrote their
own category into the `source_label` column of their copy of the sheet
(the column was named after the original CFPB label but was overwritten with
each annotator's own judgment, so the column heading is a historical
artefact).

- Owen's labels — [`Annotator__Owen.xlsx`](Annotator__Owen.xlsx)
- Russell's labels — [`Annotator__Russell.xlsx`](Annotator__Russell.xlsx)
- Final frozen labels after resolution — [`Final Golden Test Set.xlsx`](Final%20Golden%20Test%20Set.xlsx)

## Disagreement pattern (resolved on the Final set)

All 23 disagreements and their final resolution are listed by
`compute_agreement.py`. By type:

| Boundary | Count | Final resolution |
|---|---:|---|
| Bank account ↔ Money transfer or service | 14 | Bank account (hold/freeze on own account, not a transfer) |
| Credit reporting ↔ Debt collection | 5 | Credit reporting (fix the report entry) |
| Four one-off cases | 4 | mixed |

These are the same category boundaries that drove the misclassifications in
all three candidate models (see Slide 10), confirming that the hardest
category boundaries are inherent to the task rather than artefacts of any
single model.

## Protocol revisions

The labelling protocol was updated once after the first round of
disagreements:

- **v1.0** — initial 7 category definitions + 8 ordered decision rules.
  See [`Labeling Protocol v1.pdf`](Labeling%20Protocol%20v1.pdf).
- **v1.1** — added three clarifications triggered by the disagreements above.
  See [`Labeling Protocol v1.1.pdf`](Labeling%20Protocol%20v1.1.pdf).

The clarifications are Rules 2, 3 and 4 in v1.1, each tied to a specific
disagreement that revealed a gap in the protocol.
