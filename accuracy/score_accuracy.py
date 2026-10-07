"""Score accuracy runs against the golden labels and check requirement R4.

For each run folder results/<model>/accuracy/run<N>/ it reads service.jsonl
(the evidence of record) and responses.csv (the sender's view), matches each
golden ticket by request id "golden-<row>", and writes into that folder:

    predictions.csv      row, golden label, predicted category, latency, tokens
    confusion_matrix.csv golden label (rows) x predicted category (columns)
    per_category.csv     n, correct, recall, precision, R4 minimum, pass
    report.md            overall accuracy with 95% Wilson interval, R4 verdict,
                         per-category table, confusion matrix, top confusions,
                         single-request latency and token counts

It also writes results/accuracy_summary.csv with one line per run.

R4 (Requirements/Requirements.md): overall >= 80%, recall >= 70% in every
category (as counts), unclassified <= 2%.

Usage (from the repository root):
    python accuracy/score_accuracy.py                       # every accuracy run
    python accuracy/score_accuracy.py --model tev1:4b --run 1
"""

import argparse
import glob
import json
import math
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "Golden_Test_Set", "Final Golden Test Set.xlsx")

CATEGORIES = [
    "Credit reporting",
    "Debt collection",
    "Mortgage",
    "Credit card",
    "Bank account or service",
    "Consumer loan",
    "Money transfer or service",
]
UNCLASSIFIED = "unclassified"
NO_RESPONSE = "(error)"

# R4 thresholds
OVERALL_MIN = 0.80
RECALL_MIN = 0.70
UNCLASSIFIED_MAX = 0.02


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def nearest_rank(values, p):
    """p-th percentile, nearest-rank method: smallest value with >= p% at or below it."""
    v = sorted(x for x in values if x is not None and not pd.isna(x))
    if not v:
        return None
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def load_service_log(path):
    by_id = {}
    startup = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("event") == "startup":
                startup = rec
            elif rec.get("event") == "request" and rec.get("path") == "/tickets":
                rid = rec.get("request_id", "")
                if rid.startswith("golden-"):
                    by_id[rid] = rec
    return startup, by_id


def fmt(x, digits=1):
    return "-" if x is None or pd.isna(x) else f"{x:,.{digits}f}"


def score_run(run_dir, golden):
    log_path = os.path.join(run_dir, "service.jsonl")
    if not os.path.exists(log_path):
        print(f"skip {run_dir}: no service.jsonl (run sut_collect.ps1 -Test accuracy first)")
        return None
    startup, log = load_service_log(log_path)
    resp_path = os.path.join(run_dir, "responses.csv")
    responses = pd.read_csv(resp_path).set_index("row") if os.path.exists(resp_path) else None

    rows = []
    for t in golden.itertuples(index=False):
        rec = log.get(f"golden-{t.row}")
        ok = rec is not None and rec.get("status") == 200
        rows.append({
            "row": t.row,
            "golden": t.golden,
            "predicted": rec.get("category") if ok else NO_RESPONSE,
            "http_status": rec.get("status") if rec else None,
            "latency_ms": rec.get("latency_ms") if rec else None,
            "ollama_total_duration_ms": (rec.get("ollama_total_duration_ns") or float("nan")) / 1e6 if rec else None,
            "prompt_tokens": rec.get("ollama_prompt_eval_count") if rec else None,
            "output_tokens": rec.get("ollama_eval_count") if rec else None,
            "choice_confidence": rec.get("choice_confidence") if rec else None,
            "model_output": rec.get("model_output") if rec else None,
            "in_log": rec is not None,
        })
    pred = pd.DataFrame(rows)
    pred["correct"] = pred.golden == pred.predicted
    n = len(pred)

    # Cross-check the sender's view against the log
    mismatches = 0
    if responses is not None:
        joined = pred.set_index("row").join(responses[["category"]], how="left")
        sent_ok = joined.category.notna()
        mismatches = int((joined.loc[sent_ok, "category"] != joined.loc[sent_ok, "predicted"]).sum())

    k = int(pred.correct.sum())
    lo, hi = wilson(k, n)
    n_unclassified = int((pred.predicted == UNCLASSIFIED).sum())
    n_errors = int((pred.predicted == NO_RESPONSE).sum())
    n_missing = int((~pred.in_log).sum())

    # Per category
    per_cat = []
    for c in CATEGORIES:
        sub = pred[pred.golden == c]
        cn = len(sub)
        correct = int(sub.correct.sum())
        need = math.ceil(RECALL_MIN * cn)
        predicted_as_c = int((pred.predicted == c).sum())
        per_cat.append({
            "category": c,
            "n": cn,
            "correct": correct,
            "recall": correct / cn if cn else float("nan"),
            "predicted_as": predicted_as_c,
            "precision": correct / predicted_as_c if predicted_as_c else float("nan"),
            "r4_min_correct": need,
            "r4_pass": correct >= need,
        })
    per_cat = pd.DataFrame(per_cat)

    columns = CATEGORIES + [UNCLASSIFIED, NO_RESPONSE]
    cm = pd.crosstab(pd.Categorical(pred.golden, CATEGORIES), pd.Categorical(pred.predicted, columns), dropna=False)
    cm.index.name, cm.columns.name = "golden", "predicted"

    overall_need = math.ceil(OVERALL_MIN * n)
    unclassified_max = math.floor(UNCLASSIFIED_MAX * n)
    r4_overall = k >= overall_need
    r4_recall = bool(per_cat.r4_pass.all())
    r4_unclassified = n_unclassified <= unclassified_max
    r4 = r4_overall and r4_recall and r4_unclassified
    borderline = abs(k / n - OVERALL_MIN) <= 0.03

    lat = pred.latency_ms[pred.predicted != NO_RESPONSE].tolist()
    out_tok = pred.output_tokens.tolist()

    # Files
    pred.drop(columns=["in_log"]).to_csv(os.path.join(run_dir, "predictions.csv"), index=False)
    cm.to_csv(os.path.join(run_dir, "confusion_matrix.csv"))
    per_cat.to_csv(os.path.join(run_dir, "per_category.csv"), index=False)

    model = startup.get("model") if startup else "?"
    wrong = pred[~pred.correct & (pred.predicted != NO_RESPONSE)]
    top = wrong.groupby(["golden", "predicted"]).size().sort_values(ascending=False).head(8)

    md = [
        f"# Accuracy: {model}",
        "",
        f"- Run folder: `{os.path.relpath(run_dir, ROOT)}`",
        f"- Model digest: `{startup.get('model_digest') if startup else '?'}`",
        f"- Endpoint: `{startup.get('ollama_api', 'chat') if startup else '?'}`",
        f"- Golden tickets: {n}; found in service log: {n - n_missing}; HTTP errors or missing: {n_errors}",
        f"- Sender vs log category mismatches: {mismatches}",
        "",
        "## R4 verdict",
        "",
        "| Check | Required | Measured | Pass |",
        "|---|---|---|---|",
        f"| Overall accuracy | >= {overall_need}/{n} ({OVERALL_MIN:.0%}) | {k}/{n} = {k / n:.1%} (95% CI {lo:.1%} to {hi:.1%}) | {'yes' if r4_overall else 'no'} |",
        f"| Recall >= {RECALL_MIN:.0%} in every category | all 7 | {int(per_cat.r4_pass.sum())}/7 | {'yes' if r4_recall else 'no'} |",
        f"| `unclassified` | <= {unclassified_max}/{n} ({UNCLASSIFIED_MAX:.0%}) | {n_unclassified}/{n} | {'yes' if r4_unclassified else 'no'} |",
        f"| **R4** | | | **{'PASS' if r4 else 'FAIL'}**{' (borderline: overall within 3 points of 80%)' if borderline else ''} |",
        "",
        "## Per category",
        "",
        "| Category | n | Correct | Recall | Needed | Pass | Predicted as | Precision |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for r in per_cat.itertuples():
        md.append(
            f"| {r.category} | {r.n} | {r.correct} | {r.recall:.0%} | {r.r4_min_correct} | "
            f"{'yes' if r.r4_pass else 'no'} | {r.predicted_as} | {fmt(r.precision * 100, 0)}% |"
        )
    md += ["", "## Confusion matrix (rows: golden, columns: predicted)", ""]
    md.append("| golden \\ predicted | " + " | ".join(columns) + " |")
    md.append("|---|" + "---:|" * len(columns))
    for g in CATEGORIES:
        md.append(f"| {g} | " + " | ".join(str(int(cm.loc[g, c])) for c in columns) + " |")
    md += ["", "## Most frequent confusions", "", "| Golden | Predicted | Count |", "|---|---|---:|"]
    md += [f"| {g} | {p} | {c} |" for (g, p), c in top.items()]
    md += [
        "",
        "## Single-request latency (no queueing; tickets sent one at a time)",
        "",
        "Percentiles use the nearest-rank method.",
        "",
        "| | p50 | p95 | p99 | mean | max |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Service `latency_ms` (s) | {fmt(nearest_rank(lat, 50) / 1000 if lat else None, 2)} | "
        f"{fmt(nearest_rank(lat, 95) / 1000 if lat else None, 2)} | {fmt(nearest_rank(lat, 99) / 1000 if lat else None, 2)} | "
        f"{fmt(pd.Series(lat).mean() / 1000 if lat else None, 2)} | {fmt(max(lat) / 1000 if lat else None, 2)} |",
        f"| Output tokens | {fmt(nearest_rank(out_tok, 50), 0)} | {fmt(nearest_rank(out_tok, 95), 0)} | "
        f"{fmt(nearest_rank(out_tok, 99), 0)} | {fmt(pd.Series(out_tok, dtype=float).mean(), 1)} | "
        f"{fmt(pd.Series(out_tok, dtype=float).max(), 0)} |",
        "",
    ]
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"{model}: {k}/{n} = {k / n:.1%}  R4 {'PASS' if r4 else 'FAIL'}  -> {os.path.relpath(run_dir, ROOT)}/report.md")

    summary = {
        "model": model,
        "model_digest": startup.get("model_digest") if startup else None,
        "ollama_api": startup.get("ollama_api", "chat") if startup else None,
        "run": os.path.basename(run_dir),
        "n": n,
        "correct": k,
        "accuracy": k / n,
        "ci95_low": lo,
        "ci95_high": hi,
        "unclassified": n_unclassified,
        "errors": n_errors,
        "categories_passing": int(per_cat.r4_pass.sum()),
        "r4_pass": r4,
        "latency_p50_s": nearest_rank(lat, 50) / 1000 if lat else None,
        "latency_p95_s": nearest_rank(lat, 95) / 1000 if lat else None,
    }
    for r in per_cat.itertuples():
        summary[f"recall_{r.category}"] = r.recall
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="only this model, e.g. tev1:4b")
    ap.add_argument("--run", type=int, help="only this run number")
    args = ap.parse_args()

    golden = pd.read_excel(GOLDEN).rename(columns={"source_label": "golden"})[["row", "golden"]]
    unknown = set(golden.golden) - set(CATEGORIES)
    if unknown:
        sys.exit(f"golden labels not in CATEGORIES: {unknown}")

    model_glob = re.sub(r"[^A-Za-z0-9._-]", "-", args.model) if args.model else "*"
    run_glob = f"run{args.run}" if args.run else "run*"
    dirs = sorted(glob.glob(os.path.join(ROOT, "results", model_glob, "accuracy", run_glob)))
    if not dirs:
        sys.exit("no accuracy run folders found under results/")

    summaries = [s for s in (score_run(d, golden) for d in dirs) if s]
    if summaries and not (args.model or args.run):
        out = os.path.join(ROOT, "results", "accuracy_summary.csv")
        pd.DataFrame(summaries).to_csv(out, index=False)
        print(f"Summary of {len(summaries)} runs -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
