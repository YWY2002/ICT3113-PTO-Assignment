"""Summarise the Assignment 2 speed tests (Step 4) and draw the accuracy-latency chart.

For every run folder results/<config>/a2-speed/run<N>/ it reads
    results.jtl    every JMeter sample (the client's view, end to end)
    jmeter.log     how many arrivals JMeter scheduled ("Generating N events")
    loadgen.json   S, rate, run length, GET /stats before and after
    service.jsonl  the service's own log (escalation, service-side latency)
and reports, per run:
    sent         arrivals JMeter scheduled for POST /tickets
    completed    samples with HTTP 200
    errored      samples that failed (timeout, connection error, non-200)
    unfinished   sent - samples recorded (requests still open when JMeter stopped)
    p50          median end-to-end latency of the completed requests (nearest rank)
    throughput   completed requests per hour over the run (first send to last reply)
    error rate   (errored + unfinished) / sent
    escalated    cascade only: share of logged tickets with escalated = true
    network      median of JMeter elapsed - service latency_ms, matched by request id

Per configuration: p50 as the mean of the three runs with min-max spread,
p95 pooled over all completed requests of the three runs (with n),
throughput and error rate over the three runs, escalation fraction.

Writes:
    assignment2/speedtest/speed_runs.csv      one line per run
    assignment2/speedtest/speed_results.md    the tables above, plus accuracy
    figures/a2_accuracy_vs_latency.png        test-set accuracy vs speed-test p50

Usage (from the repository root):
    python assignment2/speedtest/analyse_speed.py
"""

import csv
import glob
import json
import math
import os
import re
import statistics

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "assignment2", "speedtest")
FIG = os.path.join(ROOT, "figures", "a2_accuracy_vs_latency.png")
TEST = "a2-speed"

# Display order and names
CONFIGS = [
    ("tev1-4b", "Tev1 4B"),
    ("cascade-A", "Cascade A"),
    ("clef-flash-9b", "Clef Flash 9B (top model)"),
    ("cascade-B", "Cascade B"),
    ("qwen3.8-27b", "Qwen3.8 27B"),
]
# Chart label offsets in points, so labels of points at the same accuracy do not overlap
LABEL_OFFSET = {
    "tev1-4b": (0, -18, "center"),
    "cascade-A": (0, 12, "center"),
    "clef-flash-9b": (0, 12, "center"),
    "cascade-B": (0, -18, "center"),
    "qwen3.8-27b": (-10, -18, "right"),
}
TOP = "clef-flash-9b"
OVERALL_DROP = 0.10


def nearest_rank(values, p):
    """p-th percentile, nearest-rank method: smallest value with >= p% at or below it."""
    v = sorted(values)
    if not v:
        return None
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def read_json(path):
    # PowerShell writes JSON with a byte-order mark
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def scheduled_arrivals(jmeter_log):
    """Sum of 'Generating N events' over the Open Model thread groups."""
    total = 0
    with open(jmeter_log, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.search(r"PoissonArrivalsRamp: Generating (\d+) events", line)
            if m:
                total += int(m.group(1))
    return total


def error_kind(sample):
    code = sample["responseCode"]
    if "SocketTimeout" in code:
        return "read timeout"
    if "Connect" in code:
        return "connection error"
    return f"HTTP {code}"


def load_service_log(path):
    by_id = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("event") == "request" and rec.get("path") == "/tickets":
                rid = rec.get("request_id") or ""
                if rid.startswith("t-"):
                    by_id[rid] = rec
    return by_id


def analyse_run(run_dir):
    with open(os.path.join(run_dir, "results.jtl"), encoding="utf-8") as f:
        samples = [s for s in csv.DictReader(f) if s["label"] == "POST /tickets"]
    sent = scheduled_arrivals(os.path.join(run_dir, "jmeter.log")) or len(samples)
    ok = [s for s in samples if s["success"] == "true" and s["responseCode"] == "200"]
    bad = [s for s in samples if s not in ok]
    lat_s = [int(s["elapsed"]) / 1000 for s in ok]

    starts = [int(s["timeStamp"]) for s in samples]
    ends = [int(s["timeStamp"]) + int(s["elapsed"]) for s in ok]
    window_h = (max(ends) - min(starts)) / 3_600_000 if ok else None

    log = load_service_log(os.path.join(run_dir, "service.jsonl"))
    escalated = [r for r in log.values() if r.get("escalated") is True]
    gaps = [int(s["elapsed"]) - log[s["req_id"]]["latency_ms"] for s in ok if s["req_id"] in log]

    lg = read_json(os.path.join(run_dir, "loadgen.json"))
    stored = None
    if lg.get("stats_before") and lg.get("stats_after"):
        stored = lg["stats_after"]["total"] - lg["stats_before"]["total"]

    errors = {}
    for s in bad:
        errors[error_kind(s)] = errors.get(error_kind(s), 0) + 1

    return {
        "sent": sent,
        "recorded": len(samples),
        "completed": len(ok),
        "errored": len(bad),
        "unfinished": sent - len(samples),
        "errors": errors,
        "latencies": lat_s,
        "p50": nearest_rank(lat_s, 50),
        "p95": nearest_rank(lat_s, 95),
        "max": max(lat_s) if lat_s else None,
        "throughput_h": len(ok) / window_h if window_h else None,
        "logged": len(log),
        "escalated": len(escalated),
        "network_ms": statistics.median(gaps) if gaps else None,
        "stored": stored,
        "S": lg.get("a2_S_seconds"),
        "rate_h": lg.get("a2_rate_tickets_per_h"),
    }


def test_accuracy(config):
    """Test-set accuracy from the scored a2-accuracy run (score_testset.py)."""
    p = os.path.join(ROOT, "results", config, "a2-accuracy", "run1", "predictions.csv")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return sum(r["golden"] == r["predicted"] for r in rows), len(rows)


def fmt(x, digits=1):
    return "-" if x is None else f"{x:,.{digits}f}"


def main():
    runs, summary = [], []
    for config, label in CONFIGS:
        dirs = sorted(glob.glob(os.path.join(ROOT, "results", config, TEST, "run*")))
        dirs = [d for d in dirs if os.path.exists(os.path.join(d, "metadata.json"))]
        if not dirs:
            continue
        per = []
        for d in dirs:
            r = analyse_run(d)
            r.update(config=config, label=label, run=os.path.basename(d))
            per.append(r)
            runs.append(r)

        p50s = [r["p50"] for r in per if r["p50"] is not None]
        pooled = [x for r in per for x in r["latencies"]]
        sent = sum(r["sent"] for r in per)
        failed = sum(r["errored"] + r["unfinished"] for r in per)
        logged = sum(r["logged"] for r in per)
        esc = sum(r["escalated"] for r in per)
        summary.append({
            "config": config,
            "label": label,
            "runs": len(per),
            "p50_mean": statistics.mean(p50s) if p50s else None,
            "p50_min": min(p50s) if p50s else None,
            "p50_max": max(p50s) if p50s else None,
            "p95_pooled": nearest_rank(pooled, 95),
            "n_pooled": len(pooled),
            "throughput_mean": statistics.mean([r["throughput_h"] for r in per if r["throughput_h"]]),
            "sent": sent,
            "completed": sum(r["completed"] for r in per),
            "failed": failed,
            "error_rate": failed / sent if sent else None,
            "escalation": esc / logged if (logged and config.startswith("cascade")) else None,
            "accuracy": test_accuracy(config),
        })

    # One line per run
    with open(os.path.join(OUT_DIR, "speed_runs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["config", "run", "sent", "completed", "errored", "unfinished", "errors", "p50_s", "p95_s",
                    "max_s", "throughput_per_h", "stored_by_service", "escalated", "logged", "network_median_ms"])
        for r in runs:
            w.writerow([r["config"], r["run"], r["sent"], r["completed"], r["errored"], r["unfinished"],
                        "; ".join(f"{k}: {v}" for k, v in r["errors"].items()), fmt(r["p50"], 2), fmt(r["p95"], 2),
                        fmt(r["max"], 2), fmt(r["throughput_h"], 1), r["stored"], r["escalated"], r["logged"],
                        fmt(r["network_ms"], 0)])

    s_vals = {r["S"] for r in runs}
    rate_vals = {r["rate_h"] for r in runs}
    top = next((s for s in summary if s["config"] == TOP), None)
    limit = (top["accuracy"][0] / top["accuracy"][1] - OVERALL_DROP) if top and top["accuracy"] else None

    md = [
        "# Assignment 2 speed-test results",
        "",
        "Written by `assignment2/speedtest/analyse_speed.py` from `results/*/a2-speed/run*/`.",
        "",
        f"- S = {', '.join(str(s) for s in sorted(s_vals))} s; offered rate {', '.join(str(r) for r in sorted(rate_vals))} "
        "tickets/h; 9 min of arrivals, 6 min pause, 300 s HTTP timeout; 3 runs per configuration.",
        "- Latency is JMeter's end-to-end time of completed requests (nearest-rank percentiles). "
        "Requests that timed out are counted as errors, not in the percentiles.",
        "",
        "## Per configuration",
        "",
        "| Configuration | Test-set accuracy | p50, mean of 3 runs (min-max) | p95, pooled (n) | Throughput (completed/h) "
        "| Errors + unfinished | Escalated |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        acc = f"{s['accuracy'][0]}/{s['accuracy'][1]} = {s['accuracy'][0] / s['accuracy'][1]:.1%}" if s["accuracy"] else "-"
        esc = "-" if s["escalation"] is None else f"{s['escalation']:.1%}"
        md.append(
            f"| {s['label']} | {acc} | {fmt(s['p50_mean'])} s ({fmt(s['p50_min'])}-{fmt(s['p50_max'])}) | "
            f"{fmt(s['p95_pooled'])} s ({s['n_pooled']}) | {fmt(s['throughput_mean'], 0)} | "
            f"{s['failed']}/{s['sent']} = {s['error_rate']:.1%} | {esc} |"
        )
    if top:
        md += ["", f"Speed relative to the top model (p50, mean of 3 runs; top model {fmt(top['p50_mean'])} s):", ""]
        for s in summary:
            if s["config"] != TOP and s["p50_mean"]:
                ratio = s["p50_mean"] / top["p50_mean"]
                if ratio < 1:
                    md.append(f"- {s['label']}: {1 - ratio:.0%} faster")
                else:
                    md.append(f"- {s['label']}: {ratio:.1f} times slower")

    md += [
        "",
        "## Per run",
        "",
        "| Configuration | Run | Sent | Completed | Errored | Unfinished | Errors | p50 (s) | Max (s) "
        "| Throughput (/h) | Stored by service | Escalated | Network (ms) |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in runs:
        esc = f"{r['escalated']}/{r['logged']}" if r["config"].startswith("cascade") else "-"
        md.append(
            f"| {r['label']} | {r['run']} | {r['sent']} | {r['completed']} | {r['errored']} | {r['unfinished']} | "
            f"{'; '.join(f'{k}: {v}' for k, v in r['errors'].items()) or '-'} | {fmt(r['p50'], 2)} | {fmt(r['max'], 2)} | "
            f"{fmt(r['throughput_h'], 0)} | {r['stored']} | {esc} | {fmt(r['network_ms'], 0)} |"
        )
    md += [
        "",
        "Stored by service = GET /stats after the run minus before. It can exceed Completed when the service "
        "finished a request after JMeter had given up on it.",
    ]
    with open(os.path.join(OUT_DIR, "speed_results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    # Accuracy vs latency: one point per configuration, p50 mean with min-max range
    pts = [s for s in summary if s["accuracy"] and s["p50_mean"]]
    if pts:
        os.makedirs(os.path.dirname(FIG), exist_ok=True)
        blue, ink, muted, grid = "#257de0", "#191919", "#666666", "#e6e6e6"
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
        for s in pts:
            acc = 100 * s["accuracy"][0] / s["accuracy"][1]
            ax.errorbar(s["p50_mean"], acc,
                        xerr=[[s["p50_mean"] - s["p50_min"]], [s["p50_max"] - s["p50_mean"]]],
                        fmt="o", color=blue, ms=8, mec="white", mew=2, ecolor=blue, elinewidth=2, capsize=0, zorder=3)
            dx, dy, ha = LABEL_OFFSET.get(s["config"], (8, 8, "left"))
            ax.annotate(s["label"], (s["p50_mean"], acc), xytext=(dx, dy), textcoords="offset points",
                        ha=ha, fontsize=9, color=ink)
        ax.set_xscale("log")
        ax.set_xticks([5, 10, 20, 50, 100, 200])
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_xlim(4, 260)
        ax.set_ylim(min(66, 100 * limit - 2) if limit is not None else None, 84)
        if limit is not None:
            ax.axhline(100 * limit, color=muted, lw=1, ls="--", zorder=1)
            ax.annotate(f"Overall accuracy limit {100 * limit:.1f}%", (ax.get_xlim()[1], 100 * limit),
                        xytext=(-4, 4), textcoords="offset points", ha="right", fontsize=8, color=muted)
        ax.set_xlabel("Speed-test p50 latency, s (log scale; mean of 3 runs, bar = min-max)", color=ink)
        ax.set_ylabel("Test-set accuracy (%)", color=ink)
        ax.set_title("Accuracy vs latency per configuration", loc="left", color=ink, fontsize=11)
        ax.grid(True, color=grid, lw=0.8, zorder=0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(muted)
        ax.tick_params(colors=muted)
        fig.tight_layout()
        fig.savefig(FIG)

    print(f"{len(runs)} runs -> {os.path.relpath(os.path.join(OUT_DIR, 'speed_results.md'), ROOT)}, "
          f"speed_runs.csv, {os.path.relpath(FIG, ROOT)}")


if __name__ == "__main__":
    main()
