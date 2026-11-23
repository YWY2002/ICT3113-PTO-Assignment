# Cascade escalation rule (Assignment 2, Step 2)

Supporting file for the Assignment 2 submission. Documents the cascade so
another team could implement it from this description alone. Brief-mandated
alongside the prediction record and the speed-test row list.

## Pair

| Role | Model | Ollama tag | A2 digest | API endpoint | Resident size |
|---|---|---|---|---|---:|
| Small (primary) | tev1 4B | `tev1:4b` | `7954dce22bc6…` | `/v1/systemone` | ~5.7 GB |
| Large (escalation) | Clef Flash 9B | `clef-flash:9b` | `73e026ff389b…` | `/v1/systemone` | ~14 GB |

Both models stay resident. The service is started with Ollama's keep-alive
set to infinite (`OLLAMA_KEEP_ALIVE=-1`) and `OLLAMA_MAX_LOADED_MODELS >= 2`.
Combined resident size is about 20 GB; the test host has 64 GB, so both fit
comfortably. `ollama ps` confirms both models are loaded before every run.

The pair was chosen because tev1 is the fastest Assignment 1 candidate
(single-request median ≈ 5 s) and clef-flash is the most accurate
(80% on the Assignment 1 full golden set). Qwen3.8 27B was not paired: at
single-request median ≈ 40 s it dominates any cascade's average latency
without adding accuracy over clef-flash.

## Rule

For every ticket arriving at `POST /tickets`:

1. Send the ticket to **tev1** (the small model).
2. If tev1's predicted category is in the **risky set** for the current
   setting, or tev1 returned an unreadable answer (category = `unclassified`),
   escalate: send the same ticket to **clef-flash** and return its answer.
3. Otherwise, accept tev1's answer.

This is Example method 1 from the brief (category-based). It adds no extra
model call to decide — the decision is a single set-membership check on
tev1's own predicted category — so the rule itself costs roughly 0 ms.

The service log records one line per request with:

- `escalated` (true / false),
- `final_model` (the model whose answer was returned),
- the small model's predicted category, confidence and latency,
- when escalated, the large model's predicted category, latency and Ollama
  timings in addition.

The escalation fraction is derived from the logs by counting
`escalated == true`.

## Settings tested

Two settings are tested. The risky-set membership is the only thing that
changes between them; the models, API endpoints, warm-up and measurement
procedure are identical.

| Setting | Risky set | Categories in set | Expectation |
|---|---|---:|---|
| **A** | Money transfer or service, Debt collection | 2 | Fewer escalations → faster, but may let more tev1 errors through |
| **B** | Setting A + Credit reporting | 3 | More escalations → slower, but should catch more errors |

Both risky sets are chosen from tev1's confusion matrix on the **tuning
set** (odd golden rows only); the test set is never used to design the rule.
The brief (Step 1) requires this: *"Decide which categories count as
reliable from the small model's results on the tuning set only."*

### Why these categories

On the tuning set, tev1's biggest predicted-category error sources are:

- **Money transfer or service** — tev1 frequently predicts this when the
  true label is Bank account or service. Escalating catches many
  bank-vs-money-transfer confusions, which is the largest error class across
  all three Assignment 1 models.
- **Debt collection** — tev1 confuses debt-collection language with
  closely-related categories (Credit reporting, Mortgage). Escalating these
  sends the ambiguous debt-collector narratives to the more accurate model.
- **Credit reporting** (Setting B only) — adding this escalates the next
  largest mistake class on tuning, at the cost of ~25% of tuning tickets.

The specific tuning-set counts and the predicted-vs-golden confusion matrix
are in `results/tev1-4b/a2-accuracy-tuning/run1/confusion_matrix.csv` and
`per_category.csv`.

## Cost model

With small-model latency `s_s`, large-model latency `s_l` and escalation
fraction `f`, ignoring queueing and routing overhead:

    mean cascade latency ≈ s_s + f * s_l

With tev1 ≈ 5.3 s and clef-flash ≈ 9.5 s, the cascade beats clef-alone when
`5.3 + f * 9.5 < 9.5`, that is `f < 0.44`. Setting A (narrower risky set)
is expected to stay below this fraction; Setting B (wider) may approach it.
Both are reported either way, per brief.

## What is not permitted (and is not done)

- No caching of previous classifications (brief forbids).
- No change to Ollama inference settings between configurations
  (`OLLAMA_NUM_PARALLEL=1`, context lengths unchanged, held constant).
- No fine-tuning or extra classifiers.
- The classification prompt is the same as Assignment 1 for both models.

## Reproduction

With this repository on the Assignment 1 test host (Ollama 0.40.16 with
both digests above pulled):

```powershell
.\loadtest\sut_prepare.ps1 -Model cascade-A -Api cascade -Test a2-accuracy -Run 1
python assignment2\accuracy\send_testset.py --model cascade-A --set test --run 1
.\loadtest\sut_collect.ps1 -Model cascade-A -Test a2-accuracy -Run 1
python assignment2\accuracy\score_testset.py
```

Replace `cascade-A` with `cascade-B` for Setting B. The service picks up
the risky-set definition from the `CASCADE_RISKY` environment variable set
by `sut_prepare.ps1` based on the `-Model` name.
