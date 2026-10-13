# HomeSet

HomeSet turns one sentence, such as "I have 20 minutes, a mat, and dumbbells.  Work on legs," into a numbered at-home workout plan.  It is a single-role AI agent built by Valerie Zandoli and Yadan Taino for Pursuit Cycle 2.

- **Spec:**  [HomeSet Agent PRD](https://docs.google.com/document/d/1aQLT7d2mdhh-Bz-7_5RyaNbPUfcpwV9hcpnmFPKgIxQ/edit) (the Google Doc is the source of truth; this repo follows it)
- **Design:**  `docs/architecture-v3.png` (detailed) and `docs/architecture-v1.png` (simple)
- **Data:**  the free [wger](https://wger.de/en/software/api) exercise database (read-only)

## Status (scaffold, 2026-10-13)

| Part | State |
|---|---|
| Label tables (`homeset/labels.py`) | Done, tested |
| wger client with paging, retry, and the English-translation rule (`homeset/wger.py`) | Done, tested, smoke-tested against the live service |
| Time calculator (`homeset/plan_time.py`) | Done, tested; the time model is an assumption to tune |
| Output checks, plans only (`homeset/checks.py`) | Done, tested |
| Harness: tool-call cap, regenerate once, direct path (`homeset/harness.py`) | Done, tested without a model |
| System prompt v0 (`homeset/prompt.py`) | Copied from PRD 3b |
| Model wiring (`homeset/agent.py`) | **Written, never run.**  First thing to run and fix. |
| Eval runner (`evals/run_evals.py`) | Written, never run against a model |
| Eval cases | Card, edge cases, and controls written; **Valerie writes `requests_20.json`; Yadan writes `refusals_5.json`** |

## Set up

```bash
cd ~/Desktop/Github-Projects/homeset
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then put the class API key in .env
```

## Run

```bash
python -m pytest                                   # no key or network needed
python -m homeset "I have 20 minutes, a mat, and dumbbells.  Work on legs."
python -m homeset --mock "I have 20 minutes and dumbbells.  Chest."   # canned wger data
python evals/run_evals.py evals/cases/eval_card.json                  # needs the key
```

## How it fits together

```
user message -> model + system prompt -> tool runner -> wger
                      |   ^                    |
                      |   +---- clean results -+
                      v
               output checks (plans only) -> user
 hand-off, error, or one question ------------> user  (skips the checks)
```

- The model picks labels from fixed lists (`FOCUS LABELS`, `EQUIPMENT LABELS`); code turns them into wger numbers.  The model never sees the numbers.
- Code adds `language=2`, always adds bodyweight (equipment 7), repeats a filter once per value, follows the next-page link, and marks any cut list ("showing 40 of 56").
- Every plan passes five checks before the user sees it:  exact format, names from wger, equipment the user has, total within 5 minutes, safety line.  One failed check sends the plan back once; a second failure shows a visible error and no plan.
- A request stops at 10 tool calls.

## Open items

From the PRD and the diagram:

1. **Soleus under legs.**  Yadan said to include Soleus (15) "with calves".  `legs` currently includes it (five muscles, exactly the five-search cap).  Confirm.
2. **Refusal cases.**  Pregnancy and surgery are hand-off triggers; the five refusal cases should cover them.
3. **Survey.**  Not run.  The counts go into PRD Section 1.
4. **Time model.**  3 seconds per rep, the rest given, 30 seconds between exercises.  An assumption; tune after the first run.  Timed moves such as planks are version 2.
5. **Messages with no fixed wording.**  "No exercises matched", "too few exercises", and "impossible request" have no exact sentence, so `checks.classify()` would treat them as failed plans.  Settle fixed wording (or a rule) and add it to `classify()` and the prompt.
6. **Blue items in diagram v3 (proposed, not in the PRD).**  This scaffold already keeps only English name, equipment, muscles, and category (descriptions are dropped; `include_description=True` brings them back), drops exercises that need gear the user lacks, and marks the cut.  Confirm or remove.
7. **Error wording.**  `ERROR_MESSAGE` and `BUDGET_MESSAGE` in `harness.py` are placeholders.
8. **Exercise names with parentheses** (for example "Squat (barbell)") fail the name check and get regenerated; see the note in `checks.py`.
