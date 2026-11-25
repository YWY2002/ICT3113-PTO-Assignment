# Cascade escalation rule (Assignment 2, Step 2)

Supporting file for the Assignment 2 submission. It describes the cascade
fully enough for another team to implement it from this description alone.

## Pair

| Role | Model | Ollama tag | Digest | API endpoint | Resident size |
|---|---|---|---|---|---:|
| Small (first) | Tev1 4B | `tev1:4b` | `7954dce22bc6` | `/v1/systemone` | 5.7 GB |
| Large (escalation) | Clef Flash 9B | `clef-flash:9b` | `73e026ff389b` | `/v1/systemone` | 14 GB |

Ollama 0.40.16, CPU only. Both models stay loaded: Ollama runs with
`OLLAMA_KEEP_ALIVE=-1` (models never unload) and its default limit on loaded
models, which allows three at once. Together the two models take about 20 GB
of the 64 GB host, and `ollama ps` lists both, at 100% CPU, before every
cascade run (checked by `loadtest/sut_prepare.ps1`).

Tev1 is the small model because it is the fastest candidate (tuning-set
single-request median 4.6 s). Clef Flash is the large model because it is the
top Assignment 1 model (120/150 on the full golden set). Qwen3.8 27B is not
used: its single-request median is about 40 s, so as the large model it would
make every escalated ticket slower than Clef Flash alone.

## Rule

For every ticket arriving at `POST /tickets`:

1. Classify the ticket with **Tev1**.
2. If Tev1's predicted category is in the **risky set** of the current
   setting, or Tev1's answer is unreadable (`unclassified`), escalate: classify
   the same ticket with **Clef Flash** and return Clef Flash's category.
3. Otherwise, return Tev1's category.

This is the brief's Example method 1 (category-based). Only the predicted
category can be used, because the true category is unknown when a ticket
arrives. The decision is a set-membership check on Tev1's answer, so it adds
no model call. The caller sees one category either way.

The service log records, for every ticket: `escalated` (true/false),
`final_model`, and Tev1's category, confidence and latency; for escalated
tickets also Clef Flash's category and latency. The escalation fraction is the
share of `escalated == true` lines.

## Settings

The risky set is the only thing that differs between the two settings.

| Setting | Risky set (Tev1 predicts...) | Escalated on the tuning set |
|---|---|---:|
| **A** (`cascade-A`) | Debt collection, Money transfer or service | 19/75 = 25% |
| **B** (`cascade-B`) | Setting A + Credit reporting | 40/75 = 53% |

### How the risky sets were chosen

From Tev1's results on the **tuning set** only
(`results/tev1-4b/a2-accuracy-tuning/run1/`), grouped by the category Tev1
**predicted**:

| Tev1 predicted | Tickets | Wrong | Wrong when predicted | Wrong answers were really |
|---|---:|---:|---:|---|
| Debt collection | 9 | 6 | 67% | Consumer loan 5, Mortgage 1 |
| Money transfer or service | 10 | 3 | 30% | Bank account or service 3 |
| Credit reporting | 21 | 2 | 10% | Debt collection 1, Credit card 1 |
| Bank account or service | 15 | 1 | 7% | |
| Credit card | 6 | 1 | 17% | |
| Mortgage | 10 | 1 | 10% | |
| Consumer loan | 4 | 0 | 0% | |
| **Total** | **75** | **14** | | |

- **Setting A** escalates the two predicted categories with the most wrong
  answers, which are also the two least reliable: 9 of Tev1's 14 tuning-set
  errors.
- **Setting B** adds the category with the next most wrong answers, Credit
  reporting (2 more errors). It doubles the escalation fraction, so the two
  settings show the speed-accuracy trade-off.

### What the tuning set says about the result

Clef Flash ran on the same 75 tuning tickets
(`results/clef-flash-9b/a2-accuracy-tuning/run1/`). Combining the two runs
gives the cascade's expected tuning-set result:

| | Tev1 alone | Setting A | Setting B | Clef Flash alone |
|---|---:|---:|---:|---:|
| Accuracy | 61/75 | 62/75 | 62/75 | 61/75 |
| Escalated | - | 19/75 | 40/75 | - |
| Accuracy of escalated tickets | - | 11/19 | 30/40 | - |
| Accuracy of accepted tickets | - | 51/56 | 32/35 | - |

Tev1 and Clef Flash make similar mistakes on these tickets: Clef Flash
corrects 1 of the 9 escalated errors in Setting A and none of the extra Credit
reporting ones in Setting B. The rule catches Tev1's errors, but escalation
adds little accuracy. This is reported, not tuned away: choosing categories by
what Clef Flash happens to get right on 75 tickets would fit the rule to the
tuning set.

## Cost

With Tev1 time `s_small`, Clef Flash time `s_large` and escalation fraction
`f`, ignoring queueing:

    mean cascade time = s_small + f * s_large

With the tuning-set means (Tev1 4.95 s, Clef Flash 9.56 s), the cascade is
faster than Clef Flash alone only when `f < (9.56 - 4.95) / 9.56 = 0.48`, and
it is never faster than Tev1 alone. Setting A (f = 0.25, 7.3 s) is below the
break-even; Setting B (f = 0.53, 9.9 s) is above it.

## What is not done

- No caching of classifications.
- No change to Ollama settings between configurations (Ollama defaults, plus
  `OLLAMA_KEEP_ALIVE=-1` and the CPU-only settings, the same for every run).
- No fine-tuning or extra classifier.
- The classification prompt is unchanged from Assignment 1 for both models.

## Reproduction

On the test host (Ollama 0.40.16, both digests above):

```powershell
.\loadtest\sut_prepare.ps1 -Model cascade-A -Api cascade -Test a2-accuracy -Run 1
python assignment2\accuracy\send_testset.py --model cascade-A --run 1
.\loadtest\sut_collect.ps1 -Model cascade-A -Test a2-accuracy -Run 1
python assignment2\accuracy\score_testset.py
```

Use `cascade-B` for Setting B. `sut_prepare.ps1` sets the risky set
(`CASCADE_RISKY`) from the `-Model` name.
