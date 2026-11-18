"""Send the golden test-set tickets through POST /tickets, one at a time.

Run on the system under test after loadtest/sut_prepare.ps1 -Test a2-accuracy
has printed READY, then collect with loadtest/sut_collect.ps1 -Test a2-accuracy.

Sends the rows in assignment2/split/test_rows.csv, in row order. With
--set tuning it sends tuning_rows.csv instead, into the a2-accuracy-tuning
folder (prepare and collect with -Test a2-accuracy-tuning); those results are
for designing the escalation rule only and are never reported as accuracy.

Each ticket is sent with X-Request-ID "golden-<row>", so the service log line
for it can be matched to its golden label. Tickets are sent sequentially:
this is an accuracy test, not a load test, so there is no queueing and each
request's latency is the single-request service time.

Writes results/<model>/a2-accuracy/run<N>/responses.csv:
    row, request_id, http_status, category, client_latency_ms, error

Usage (from the repository root):
    python assignment2/accuracy/send_testset.py --model tev1:4b --run 1
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
GOLDEN = os.path.join(ROOT, "Golden_Test_Set", "Final Golden Test Set.xlsx")
SPLIT_DIR = os.path.join(ROOT, "assignment2", "split")
TEST_NAME = {"test": "a2-accuracy", "tuning": "a2-accuracy-tuning"}


def run_dir(model, test, run):
    model_dir = re.sub(r"[^A-Za-z0-9._-]", "-", model)
    return os.path.join(ROOT, "results", model_dir, test, f"run{run}")


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
    ap.add_argument("--set", dest="which", choices=["test", "tuning"], default="test",
                    help="which half of the golden split to send (default: test)")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--timeout", type=float, default=900, help="seconds per request (service gives up at 600)")
    args = ap.parse_args()

    test = TEST_NAME[args.which]
    out_dir = run_dir(args.model, test, args.run)
    if not os.path.isdir(out_dir):
        sys.exit(f"{out_dir} not found. Run loadtest/sut_prepare.ps1 -Test {test} -Run {args.run} first.")
    out_csv = os.path.join(out_dir, "responses.csv")
    if os.path.exists(out_csv):
        sys.exit(f"{out_csv} already exists; use another --run.")

    golden = pd.read_excel(GOLDEN)
    if golden.row.duplicated().any():
        sys.exit("golden set has duplicate row numbers")
    golden = golden.set_index("row")
    rows = sorted(pd.read_csv(os.path.join(SPLIT_DIR, f"{args.which}_rows.csv"), encoding="utf-8-sig")["row"])
    missing = [r for r in rows if r not in golden.index]
    if missing:
        sys.exit(f"rows not in the golden set: {missing}")
    n = len(rows)
    print(f"Sending {n} {args.which}-set tickets to {args.base_url} as {args.model}, run {args.run}")

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "request_id", "http_status", "category", "client_latency_ms", "error"])
        for i, row in enumerate(rows, 1):
            request_id = f"golden-{row}"
            status, category, ms, err = post_ticket(args.base_url, golden.loc[row, "narrative"], request_id, args.timeout)
            w.writerow([row, request_id, status, category, round(ms, 1), err])
            f.flush()
            print(f"  {i:3}/{n}  row {row}  {status}  {category}  {ms / 1000:.1f} s")

    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
