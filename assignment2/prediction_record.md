# Assignment 2 prediction record (Step 3)
Inputs, all from runs already in the repository:

- Accuracy limits and single-model test-set accuracy:
  `assignment2/accuracy/accuracy_results.md` (overall limit 68.7%;
  Tev1 60/75, Clef Flash 59/75, Qwen3.8 61/75, all passing).
- Tuning-set runs of Tev1 and Clef Flash:
  `results/tev1-4b/a2-accuracy-tuning/run1/`,
  `results/clef-flash-9b/a2-accuracy-tuning/run1/`, and the cascade rule in
  `assignment2/cascade/RULE.md`.
- Single-request times on the tuning set: Tev1 median 4.6 s (mean 4.95 s),
  Clef Flash median 9.1 s (mean 9.56 s). Qwen3.8 on the test set: median 39.6 s.

## P1. Speed-test set-up

- S (middle of three typical tickets on Clef Flash) will be **8 to 10 s**, so
  the test rate is about **200 tickets/h** (one every 18 s), each run about
  **9 minutes and 30 tickets**.
- That rate is above the client's Expected peak of 167 tickets/h
  (Assignment 1 workload model), so a configuration that keeps up at the test
  rate also handles the client's peak.

## P2. The fastest configuration within the limits is Tev1 alone

- Tev1 passes both limits (60/75 on the test set) and has the shortest
  service time. Every cascade adds Clef Flash's time to a share of tickets on
  top of Tev1's, so no cascade setting can be faster than Tev1 alone.
- Expected speed-test p50 (mean of three runs), using Kingman's formula at
  one arrival every 18 s with Poisson arrivals:

| Configuration | Utilisation | Predicted p50 | Keeps up? |
|---|---:|---:|---|
| Tev1 alone | 0.28 | **5 to 7 s** | yes |
| Cascade A | 0.40 | **6 to 9 s** | yes |
| Clef Flash alone (top model) | 0.53 | **10 to 15 s** | yes |
| Cascade B | 0.55 | **11 to 16 s** | yes |
| Qwen3.8 alone | > 2 | **over 100 s** | **no** |

- Ranking by p50: Tev1 < Cascade A < Clef Flash < Cascade B < Qwen3.8.
  Cascade A beats Clef Flash alone; Cascade B does not, because it escalates
  more than the 48% break-even.
- Tev1 alone will be **at least 30% faster** than Clef Flash alone at p50.
- **Qwen3.8 cannot keep up**: it needs about 40 s per ticket and a ticket
  arrives every 18 s, so the queue grows for the whole run. At least
  **one third of its requests will exceed the 300 s timeout or be unfinished**.
- No errors (non-200 responses) for any configuration other than Qwen3.8.

## P3. The cascade, per setting

| | Setting A | Setting B |
|---|---|---|
| Escalated on the test set | **20% to 35%** (tuning: 25%) | **45% to 60%** (tuning: 53%) |
| Test-set accuracy | **59 to 62 of 75** (79% to 83%); passes both limits | **59 to 62 of 75**; passes both limits |
| Accuracy vs Tev1 alone (60/75) | within 2 tickets | within 2 tickets |
| Accuracy-test median latency (single request) | **5 to 7 s** | **9 to 12 s** |
| Speed-test p50 | 6 to 9 s (P2) | 11 to 16 s (P2) |
| Escalated in the speed test | **within 15 points of the test-set figure** | **within 15 points of the test-set figure** |

- Escalated tickets will be less accurate than accepted ones in both
  settings (tuning: A 11/19 vs 51/56; B 30/40 vs 32/35), because the rule
  sends Tev1's least reliable answers to a model that gets most of the same
  tickets wrong.
- Neither setting will be more accurate than the better single model by more
  than 2 tickets: on the tuning set Tev1 and Clef Flash have the same accuracy
  (61/75) and escalation gained one ticket.

## P4. Categories that lose the most when Tev1's answer is accepted

Compared with the top model (Clef Flash), on the test set:

1. **Consumer loan** loses the most. Tev1 labels consumer-loan tickets as
   Debt collection (5 of its 6 Debt collection errors on the tuning set) and
   scored 4/10 against Clef Flash's 6/10 there. The cascade escalates those
   tickets but Clef Flash fixes few of them. With 4 test tickets, the
   category is too small for a fair per-category test.
2. **Money transfer or service** loses next (tuning: Tev1 7/8, Clef Flash
   8/8). With 8 test tickets, one ticket is 12.5 points.
3. **Bank account or service** gains: Tev1 scored 14/18 on the tuning set
   against Clef Flash's 11/18.

Both cascade settings will pass every per-category limit.
