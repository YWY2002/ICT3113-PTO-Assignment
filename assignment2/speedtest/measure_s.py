"""Measure S for one model: single-request service time on 3 typical tickets.

Procedure from the Assignment 2 brief:
    "Restart Ollama and do the normal warm-up. Then send three different
     tickets of typical length to your top model, one at a time, and take
     the middle time."

Run on the system under test after loadtest/sut_prepare.ps1 -Test a2-speed-S
has printed READY (which now sends the three fixed warm-up tickets first).
The three tickets sent here are the first three rows of the typical bucket in
assignment2/speedtest/speedtest_rows.csv (5009, 5026, 5093), all non-golden.

Writes results/<model>/a2-speed-S/run<N>/
    s_measurement.csv   row, request_id, http_status, category, client_latency_ms
    s_measurement.json  model, run, three timings in seconds, middle time (S),
                        derived rate (3600 / (2 * S) tickets/h) and run length
                        (max(5, S) minutes)

Usage:
    python assignment2/speedtest/measure_s.py --model clef-flash:9b --run 1
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE = os.path.join(ROOT, "data", "ict3113_tickets.csv")
TEST = "a2-speed-S"
SPEED_ROWS = [5009, 5026, 5093]


def run_dir(model, run):
    model_dir = re.sub(r"[^A-Za-z0-9._-]", "-", model)
    return os.path.join(ROOT, "results", model_dir, TEST, f"run{run}")


def post_ticket(base_url, narrative, request_id, timeout):
    req = urllib.request.Request(
        f"{base_url}/tickets",
        data=json.dumps({"narrative": narrative}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Request-ID": request_id},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            return resp.status, body.get("category"), (time.perf_counter() - t0) * 1000, ""
    except urllib.error.HTTPError as e:
        return e.code, None, (time.perf_counter() - t0) * 1000, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:
        return None, None, (time.perf_counter() - t0) * 1000, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Ollama tag the service is running, e.g. clef-flash:9b")
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--timeout", type=float, default=900)
    args = ap.parse_args()

    out_dir = run_dir(args.model, args.run)
    if not os.path.isdir(out_dir):
        sys.exit(f"{out_dir} not found. Run: .\\loadtest\\sut_prepare.ps1 -Model {args.model} -Api <chat|systemone> -Test {TEST} -Run {args.run}")
    out_csv = os.path.join(out_dir, "s_measurement.csv")
    out_json = os.path.join(out_dir, "s_measurement.json")
    if os.path.exists(out_csv):
        sys.exit(f"{out_csv} already exists; use another --run.")

    tickets = pd.read_csv(SOURCE, encoding="utf-8")
    tickets = tickets.set_index("row")
    missing = [r for r in SPEED_ROWS if r not in tickets.index]
    if missing:
        sys.exit(f"rows not in the dataset: {missing}")

    print(f"Sending 3 speed-S tickets to {args.base_url} as {args.model}, run {args.run}")
    print(f"Rows: {SPEED_ROWS}")

    results = []
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "request_id", "http_status", "category", "client_latency_ms"])
        for i, row in enumerate(SPEED_ROWS, 1):
            request_id = f"speed-s-{row}"
            status, category, ms, err = post_ticket(args.base_url, tickets.loc[row, "narrative"], request_id, args.timeout)
            w.writerow([row, request_id, status, category, round(ms, 1)])
            f.flush()
            results.append({"row": row, "status": status, "category": category, "ms": ms, "error": err})
            marker = "" if status == 200 else f"  ERROR: {err}"
            print(f"  {i}/3  row {row}  {status}  {category}  {ms / 1000:.2f} s{marker}")

    if any(r["status"] != 200 for r in results):
        sys.exit("one or more requests failed; S cannot be computed")

    timings_s = sorted(r["ms"] / 1000 for r in results)
    s = timings_s[1]
    rate_per_h = 3600 / (2 * s)
    run_minutes = max(5.0, s)

    summary = {
        "model": args.model,
        "run": args.run,
        "rows": SPEED_ROWS,
        "timings_s_sent_order": [round(r["ms"] / 1000, 2) for r in results],
        "timings_s_sorted": [round(t, 2) for t in timings_s],
        "S_seconds": round(s, 2),
        "rate_tickets_per_hour": round(rate_per_h, 1),
        "interarrival_seconds": round(2 * s, 2),
        "run_length_minutes": round(run_minutes, 2),
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print()
    print(f"Timings (sent order): {summary['timings_s_sent_order']} s")
    print(f"Timings (sorted):     {summary['timings_s_sorted']} s")
    print(f"S (middle)          = {summary['S_seconds']} s")
    print(f"Rate                = {summary['rate_tickets_per_hour']} tickets/h  (one every {summary['interarrival_seconds']} s)")
    print(f"Run length          = {summary['run_length_minutes']} min")
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()
