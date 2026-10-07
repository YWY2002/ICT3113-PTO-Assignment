"""Send every golden-set ticket through POST /tickets, one at a time.

Run on the system under test after loadtest/sut_prepare.ps1 -Test accuracy
has printed READY, then collect with loadtest/sut_collect.ps1 -Test accuracy.

Each ticket is sent with X-Request-ID "golden-<row>", so the service log line
for it can be matched to its golden label. Tickets are sent sequentially:
this is an accuracy test, not a load test, so there is no queueing and each
request's latency is the model's single-request service time.

Writes results/<model>/accuracy/run<N>/responses.csv:
    row, request_id, http_status, category, client_latency_ms, error

Usage (from the repository root):
    python accuracy/send_golden.py --model tev1:4b --run 1
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "Golden_Test_Set", "Final Golden Test Set.xlsx")


def run_dir(model, run):
    model_dir = re.sub(r"[^A-Za-z0-9._-]", "-", model)
    return os.path.join(ROOT, "results", model_dir, "accuracy", f"run{run}")


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
    except Exception as e:  # timeouts, connection errors
        return None, None, (time.perf_counter() - t0) * 1000, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Ollama tag the service is running, e.g. tev1:4b")
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--timeout", type=float, default=900, help="seconds per request (service gives up at 600)")
    args = ap.parse_args()

    out_dir = run_dir(args.model, args.run)
    if not os.path.isdir(out_dir):
        sys.exit(f"{out_dir} not found. Run loadtest/sut_prepare.ps1 -Test accuracy -Run {args.run} first.")
    out_csv = os.path.join(out_dir, "responses.csv")
    if os.path.exists(out_csv):
        sys.exit(f"{out_csv} already exists; use another --run.")

    golden = pd.read_excel(GOLDEN)
    n = len(golden)
    print(f"Sending {n} golden tickets to {args.base_url} as {args.model}, run {args.run}")

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "request_id", "http_status", "category", "client_latency_ms", "error"])
        for i, t in enumerate(golden.itertuples(index=False), 1):
            request_id = f"golden-{t.row}"
            status, category, ms, err = post_ticket(args.base_url, t.narrative, request_id, args.timeout)
            w.writerow([t.row, request_id, status, category, round(ms, 1), err])
            f.flush()
            print(f"  {i:3}/{n}  row {t.row}  {status}  {category}  {ms / 1000:.1f} s")

    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
