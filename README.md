# HomeSet

HomeSet turns one sentence, such as "I have 20 minutes, a mat, and dumbbells.  Work on legs," into a numbered at-home workout plan.  It is a single-role AI agent built by Valerie Zandoli and Yadan Taino for Pursuit Cycle 2.

- **Spec:**  [HomeSet Agent PRD](https://docs.google.com/document/d/1aQLT7d2mdhh-Bz-7_5RyaNbPUfcpwV9hcpnmFPKgIxQ/edit) (the Google Doc is the source of truth; this repo follows it)
- **Design:**  `docs/architecture-v3.png` (detailed) and `docs/architecture-v1.png` (simple)
- **Data:**  the free [wger](https://wger.de/en/software/api) exercise database (read-only)

## Status (2026-10-13, end of day)

| Part | State |
|---|---|
| Label tables (`homeset/labels.py`) | Done, tested |
| wger client with paging, retry, and the English-translation rule (`homeset/wger.py`) | Done, tested, smoke-tested against the live service |
| Time calculator (`homeset/plan_time.py`) | Done, tested; the time model is an assumption to tune |
| Output checks, plans only (`homeset/checks.py`) | Done, tested |
| Harness: tool-call cap, regenerate once, direct path (`homeset/harness.py`) | Done, tested without a model |
| System prompt v0 (`homeset/prompt.py`) | Copied from PRD 3b |
| Model wiring (`homeset/agent.py`) | **Run live 2026-10-13** with the class key:  Eval Card 6 of 6, edge cases 5 of 5, controls 5 of 5 matched the expected kind.  The notes (counts, ranges) are not yet graded by two people. |
| Eval runner (`evals/run_evals.py`) | Works live; checks kind, opening wording, and banned words; saves runs to `runs/` (git-ignored) |
| Eval cases | Card, edge cases, controls, multi-turn, injection, and regression cases written; the last three ran live 2026-10-14 and all matched the expected kind (notes not yet graded by two people).  `requests_20.json` is a **draft for Valerie to review before any run**.  **Yadan writes `refusals_5.json`.** |

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
python evals/run_evals.py evals/cases/eval_card.json --only case3_adversarial
python evals/run_evals.py evals/cases/multi_turn.json                 # conversations; needs the key
python evals/run_evals.py evals/cases/injection.json                  # poisoned description, notes, aliases
python evals/run_evals.py evals/cases/regressions.json                # failures found in real runs
python scripts/scan_wger_text.py                                    # live wger text; run before the demo
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
- Guarantees are tested in code with no model (`tests/test_guarantees.py`):  only labels reach wger, only GET requests leave, only wger links are followed, and every free-text field except the name is dropped.
- Every failure found live gets a row in `docs/regressions.md` and a test or case in the same commit as the fix.

## Open items

From the PRD and the diagram:

1. **Soleus under legs.**  Yadan said to include Soleus (15) "with calves".  `legs` currently includes it (five muscles, exactly the five-search cap).  Confirm.
2. **Refusal cases.**  Pregnancy and surgery are hand-off triggers; the five refusal cases should cover them.
3. **Survey.**  Not run.  The counts go into PRD Section 1.
4. **Time model.**  3 seconds per rep, the rest given, 30 seconds between exercises.  An assumption; tune after the first run.  Timed moves such as planks are version 2.
5. **Fixed wording for the no-plan messages.**  Drafted in `docs/fixed-messages.md` and already used by the code and prompt; **PRD Section 3b still has the looser v0 wording**.  Agree it, then update the Google Doc.  Includes a 10 to 45 minute range.
6. **Blue items in diagram v3 (proposed, not in the PRD).**  This repo already keeps only English name, equipment, muscles, and category (descriptions are dropped; `include_description=True` brings them back), drops exercises that need gear the user lacks, marks the cut, and drops exercise names that are sentences or longer than 45 characters (an injection filter).  Confirm or remove.
7. **Visible-error wording.**  `ERROR_MESSAGE` and `BUDGET_MESSAGE` in `harness.py` are placeholders.
