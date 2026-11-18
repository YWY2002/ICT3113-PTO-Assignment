"""Score test-set accuracy runs and check them against the Assignment 2 limits.

For each run folder results/<config>/a2-accuracy/run<N>/ it reads service.jsonl
(the evidence of record) and responses.csv (the sender's view), matches each
test-set ticket by request id "golden-<row>", and writes into that folder:

    predictions.csv      row, golden label, predicted category, latency, and
                         for the cascade, escalated and final_model
    confusion_matrix.csv golden label (rows) x predicted category (columns)
    per_category.csv     n, correct, accuracy
    report.md            overall and per-category accuracy with counts,
                         confusion matrix, escalation (cascade only),
                         single-request latency

The limits come from the top model's run:
    overall       top model's test-set accuracy - 10 percentage points
    per category  top model's test-set accuracy in that category - 15 points

The top model is the most accurate Assignment 1 model on the full golden set:
clef-flash:9b with 120/150 (both tev1:4b and qwen3.8:27b scored 119/150).

It also writes assignment2/accuracy/accuracy_results.md: the limits, every
configuration checked against them, and each model's Assignment 1 result on
the same test rows, with both digests, for comparison.

Usage (from the repository root):
    python assignment2/accuracy/score_testset.py            # every configuration, run 1
    python assignment2/accuracy/score_testset.py --run 2
"""

import argparse
import glob
import json
import math
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLDEN = os.path.join(ROOT, "Golden_Test_Set", "Final Golden Test Set.xlsx")
TEST_ROWS = os.path.join(ROOT, "assignment2", "split", "test_rows.csv")
SUMMARY = os.path.join(ROOT, "assignment2", "accuracy", "accuracy_results.md")

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

# Assignment 2 limits
TOP_MODEL = "clef-flash:9b"
OVERALL_DROP = 0.10
CATEGORY_DROP = 0.15
SMALL_CATEGORY = 10  # fewer test tickets than this: flagged as too small for a fair per-category test
EPS = 1e-9  # so that a configuration exactly on a limit passes


def model_dir(model):
    return re.sub(r"[^A-Za-z0-9._-]", "-", model)


def nearest_rank(values, p):
    """p-th percentile, nearest-rank method: smallest value with >= p% at or below it."""
    v = sorted(x for x in values if x is not None and not pd.isna(x))
    if not v:
        return None
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def pct(k, n):
    return f"{k}/{n} = {k / n:.1%}" if n else "-"


def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


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
    return startup or {}, by_id


def score_run(run_dir, golden):
    log_path = os.path.join(run_dir, "service.jsonl")
    if not os.path.exists(log_path):
        print(f"skip {os.path.relpath(run_dir, ROOT)}: no service.jsonl (run sut_collect.ps1 -Test a2-accuracy first)")
        return None
    startup, log = load_service_log(log_path)
    meta = read_json(os.path.join(run_dir, "metadata.json"))
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
            "choice_confidence": rec.get("choice_confidence") if rec else None,
            "escalated": rec.get("escalated") if rec else None,
            "final_model": rec.get("final_model", rec.get("model")) if rec else None,
            "model_output": rec.get("model_output") if rec else None,
            "in_log": rec is not None,
        })
    pred = pd.DataFrame(rows)
    pred["correct"] = pred.golden == pred.predicted
    n = len(pred)
    k = int(pred.correct.sum())

    # Cross-check the sender's view against the log
    mismatches = 0
    if responses is not None:
        joined = pred.set_index("row").join(responses[["category"]], how="left")
        sent_ok = joined.category.notna()
        mismatches = int((joined.loc[sent_ok, "category"] != joined.loc[sent_ok, "predicted"]).sum())

    n_unclassified = int((pred.predicted == UNCLASSIFIED).sum())
    n_errors = int((pred.predicted == NO_RESPONSE).sum())
    n_missing = int((~pred.in_log).sum())
    unknown = sorted(set(pred.predicted) - set(CATEGORIES) - {UNCLASSIFIED, NO_RESPONSE})

    # Per category
    per_cat = []
    for c in CATEGORIES:
        sub = pred[pred.golden == c]
        per_cat.append({
            "category": c,
            "n": len(sub),
            "correct": int(sub.correct.sum()),
            "accuracy": sub.correct.mean() if len(sub) else float("nan"),
        })
    per_cat = pd.DataFrame(per_cat)

    columns = CATEGORIES + [UNCLASSIFIED, NO_RESPONSE] + unknown
    cm = pd.crosstab(pd.Categorical(pred.golden, CATEGORIES), pd.Categorical(pred.predicted, columns), dropna=False)
    cm.index.name, cm.columns.name = "golden", "predicted"

    # Cascade only: escalation, from the service log
    is_cascade = bool(pred.escalated.notna().any())
    escalated = pred[pred.escalated.eq(True)]
    accepted = pred[pred.escalated.eq(False)]

    lat = pred.latency_ms[pred.predicted != NO_RESPONSE].tolist()

    # Files
    pred.drop(columns=["in_log"]).to_csv(os.path.join(run_dir, "predictions.csv"), index=False)
    cm.to_csv(os.path.join(run_dir, "confusion_matrix.csv"))
    per_cat.to_csv(os.path.join(run_dir, "per_category.csv"), index=False)

    config = os.path.basename(os.path.dirname(os.path.dirname(run_dir)))
    md = [
        f"# Test-set accuracy: {config}",
        "",
        f"- Run folder: `{os.path.relpath(run_dir, ROOT)}`",
        f"- Model: `{startup.get('model', '?')}`, digest `{startup.get('model_digest', '?')}`",
        f"- Endpoint: `{startup.get('ollama_api', '?')}`",
        f"- Ollama: {version(meta.get('ollama_version'))}",
        f"- Test-set tickets: {n}; found in service log: {n - n_missing}; HTTP errors or missing: {n_errors}; "
        f"`unclassified`: {n_unclassified}",
        f"- Sender vs log category mismatches: {mismatches}",
        "",
        f"**Overall: {pct(k, n)}**",
        "",
        "## Per category",
        "",
        "| Category | Correct / n | Accuracy |",
        "|---|---:|---:|",
    ]
    md += [f"| {r.category} | {r.correct}/{r.n} | {r.accuracy:.1%} |" for r in per_cat.itertuples()]
    if is_cascade:
        md += [
            "",
            "## Escalation",
            "",
            f"- Escalated: {pct(len(escalated), n)}",
            f"- Accuracy of escalated tickets: {pct(int(escalated.correct.sum()), len(escalated))}",
            f"- Accuracy of non-escalated tickets: {pct(int(accepted.correct.sum()), len(accepted))}",
        ]
    md += ["", "## Confusion matrix (rows: golden, columns: predicted)", ""]
    md.append("| golden \\ predicted | " + " | ".join(columns) + " |")
    md.append("|---|" + "---:|" * len(columns))
    for g in CATEGORIES:
        md.append(f"| {g} | " + " | ".join(str(int(cm.loc[g, c])) for c in columns) + " |")
    if lat:
        md += [
            "",
            "## Single-request latency (no queueing; tickets sent one at a time)",
            "",
            "Percentiles use the nearest-rank method. Not a speed-test result.",
            "",
            "| | p50 | p95 | max |",
            "|---|---:|---:|---:|",
            f"| Service `latency_ms` (s) | {nearest_rank(lat, 50) / 1000:.2f} | {nearest_rank(lat, 95) / 1000:.2f} | "
            f"{max(lat) / 1000:.2f} |",
        ]
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"{config}: {pct(k, n)}  -> {os.path.relpath(run_dir, ROOT)}/report.md")

    return {
        "config": config,
        "n": n,
        "correct": k,
        "per_cat": per_cat,
        "errors": n_errors,
        "escalated": len(escalated) if is_cascade else None,
        "digest": startup.get("model_digest"),
        "ollama_version": meta.get("ollama_version"),
    }


def assignment1_on_test_rows(config, test_rows):
    """The same model's Assignment 1 accuracy run, restricted to the test rows."""
    a1_dir = os.path.join(ROOT, "results", config, "accuracy", "run1")
    p = os.path.join(a1_dir, "predictions.csv")
    if not os.path.exists(p):
        return None
    a1 = pd.read_csv(p)
    a1 = a1[a1.row.isin(test_rows)]
    meta = read_json(os.path.join(a1_dir, "metadata.json"))
    return int((a1.golden == a1.predicted).sum()), len(a1), meta.get("model_digest"), meta.get("ollama_version")


def version(v):
    return v.replace("ollama version is ", "") if v else "?"


def short(digest):
    return f"`{digest[:12]}`" if digest else "?"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=int, default=1, help="run number to score (default 1)")
    args = ap.parse_args()

    test_rows = set(pd.read_csv(TEST_ROWS, encoding="utf-8-sig")["row"])
    golden = pd.read_excel(GOLDEN).rename(columns={"source_label": "golden"})[["row", "golden"]]
    unknown = set(golden.golden) - set(CATEGORIES)
    if unknown:
        sys.exit(f"golden labels not in CATEGORIES: {unknown}")
    golden = golden[golden.row.isin(test_rows)].sort_values("row")
    if len(golden) != len(test_rows):
        sys.exit("test_rows.csv has rows that are not in the golden set")

    dirs = sorted(glob.glob(os.path.join(ROOT, "results", "*", "a2-accuracy", f"run{args.run}")))
    if not dirs:
        sys.exit(f"no a2-accuracy/run{args.run} folders found under results/")
    results = [s for s in (score_run(d, golden) for d in dirs) if s]

    top = next((r for r in results if r["config"] == model_dir(TOP_MODEL)), None)
    if top is None:
        sys.exit(f"{TOP_MODEL} has no scored a2-accuracy/run{args.run}; the limits come from it, so run it first")

    top_acc = top["correct"] / top["n"]
    overall_limit = top_acc - OVERALL_DROP
    cat_limit = {r.category: r.accuracy - CATEGORY_DROP for r in top["per_cat"].itertuples()}

    md = [
        "# Assignment 2 accuracy results (test set)",
        "",
        f"Written by `assignment2/accuracy/score_testset.py` from `results/*/a2-accuracy/run{args.run}/`.",
        "",
        "## Limits",
        "",
        f"Top Assignment 1 model: `{TOP_MODEL}` (120/150 on the full golden set). "
        f"On the test set: {pct(top['correct'], top['n'])}.",
        "",
        f"- **Overall limit: {overall_limit:.1%}** (top model minus 10 points)",
        "- Per-category limit: top model minus 15 points in each category",
        "",
        "| Category | Test tickets | Top model | Limit | Note |",
        "|---|---:|---:|---:|---|",
    ]
    for r in top["per_cat"].itertuples():
        note = f"too small for a fair test: one ticket = {1 / r.n:.1%}" if r.n < SMALL_CATEGORY else ""
        md.append(f"| {r.category} | {r.n} | {r.correct}/{r.n} = {r.accuracy:.1%} | {cat_limit[r.category]:.1%} | {note} |")

    md += [
        "",
        "## Configurations",
        "",
        "Each category shows correct / n; `(below)` marks a category more than 15 points below the top model.",
        "",
        "| Configuration | Overall | " + " | ".join(CATEGORIES) + " | Overall limit | Category limits | Passes |",
        "|---|---:|" + "---:|" * len(CATEGORIES) + "---|---|---|",
    ]
    for r in results:
        overall_ok = r["correct"] / r["n"] >= overall_limit - EPS
        cells, cats_ok = [], True
        for c in r["per_cat"].itertuples():
            ok = c.n == 0 or c.accuracy >= cat_limit[c.category] - EPS
            cats_ok = cats_ok and ok
            cells.append(f"{c.correct}/{c.n}" + ("" if ok else " (below)"))
        md.append(
            f"| {r['config']} | {pct(r['correct'], r['n'])} | " + " | ".join(cells) +
            f" | {'pass' if overall_ok else 'FAIL'} | {'pass' if cats_ok else 'FAIL'} | "
            f"**{'yes' if overall_ok and cats_ok else 'no'}** |"
        )

    cascades = [r for r in results if r["escalated"] is not None]
    if cascades:
        md += ["", "## Escalation", "", "| Configuration | Escalated |", "|---|---:|"]
        md += [f"| {r['config']} | {pct(r['escalated'], r['n'])} |" for r in cascades]

    md += [
        "",
        "## Comparison with Assignment 1",
        "",
        "Each model's Assignment 1 accuracy run, scored on the same test rows. Not reused: "
        "every Assignment 2 figure above comes from the Assignment 2 run. Where the digest or "
        "Ollama version differs, a gap may come from that change.",
        "",
        "| Configuration | Assignment 2 | Digest | Ollama | Assignment 1, test rows | Digest | Ollama |",
        "|---|---:|---|---|---:|---|---|",
    ]
    for r in results:
        a1 = assignment1_on_test_rows(r["config"], test_rows)
        if a1:
            k1, n1, d1, v1 = a1
            md.append(
                f"| {r['config']} | {pct(r['correct'], r['n'])} | {short(r['digest'])} | {version(r['ollama_version'])} | "
                f"{pct(k1, n1)} | {short(d1)} | {version(v1)} |"
            )

    with open(SUMMARY, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"Limits from {TOP_MODEL}: overall {overall_limit:.1%}  -> {os.path.relpath(SUMMARY, ROOT)}")


if __name__ == "__main__":
    main()
