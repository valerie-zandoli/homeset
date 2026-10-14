# HomeSet

HomeSet turns one sentence into a numbered at-home workout plan.

Example:  "I have 20 minutes, a mat, and dumbbells.  Work on legs."

HomeSet is a single-role AI agent built by Valerie Zandoli and Yadan Taino for Pursuit L2 Cycle 2.

- **Spec:**  [HomeSet Agent PRD](https://docs.google.com/document/d/1aQLT7d2mdhh-Bz-7_5RyaNbPUfcpwV9hcpnmFPKgIxQ/edit) (the Google Doc is the source of truth; this repo follows it)
- **Design:**  `docs/architecture-v3.png` (detailed) and `docs/architecture-v1.png` (simple)
- **Data:**  the free [wger](https://wger.de/en/software/api) exercise database (read-only)

## Status (2026-10-14)

| Part | State |
|---|---|
| Label tables (`homeset/labels.py`) | Done, tested |
| wger client with paging, retry, and the English-translation rule (`homeset/wger.py`) | Done, tested, smoke-tested against the live service |
| Time calculator (`homeset/plan_time.py`) | Done, tested; the time model is an assumption to tune |
| Output checks, plans only (`homeset/checks.py`) | Done, tested |
| Harness: tool-call cap, regenerate once, direct path (`homeset/harness.py`) | Done, tested without a model |
| "(assumed)" marker (`homeset/assumed.py`) | Code writes it from the user's words and the alias table; 36 tests, no model, including all 20 request-set A inputs; not yet re-run live |
| System prompt v0 (`homeset/prompt.py`) | PRD 3b with two changes:  step 7 aims within 2 minutes (agreed by Yadan), and the model no longer writes "(assumed)" (PRD 3b to match; Yadan to confirm) |
| Model wiring (`homeset/agent.py`) | **Run live 2026-10-13** with a personal Pursuit-issued key:  Eval Card 6 of 6, edge cases 5 of 5, controls 5 of 5 matched the expected kind.  The notes (counts, ranges) are not yet graded by two people. |
| Eval runner (`evals/run_evals.py`) | Works live; checks kind, opening wording, and banned words; saves runs to `runs/` (git-ignored) |
| Eval cases | Written: card, edge cases, controls, multi-turn, injection, and regression.  The last three ran live 2026-10-14 and all matched the expected kind (notes not yet graded by two people).  The 20-request set (`requests_20.json`) was reviewed and approved by Valerie on 2026-10-14 and ran live the same day:  20 of 20 matched the expected kind, and every total landed within 5 minutes of the request.  Graded by one reader against the file's seven rules, 9 of 20 pass every rule (the headline score; the harness checks alone score 20 of 20).  The 11 misses fail only the exercise-count range (about 5 minutes per exercise against the 3.5 the ranges assumed), and one of those (a15) also lacks the "(assumed)" marker.  The ranges stay as approved; a second range set will follow the stopwatch trial (Open item 4), which replaces the assumed minutes per exercise with a measured number.  The refusal set (`refusals_5.json`, Yadan's five cases; target 4 hand-offs and 1 clarifying question) is written and has not run yet; see Open item 2. |

## Set up

```bash
cd ~/Desktop/Github-Projects/homeset
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then put your personal API key in .env
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
2. **Refusal cases (Yadan; written 2026-10-14, not yet run).**  Yadan wrote the five in `evals/cases/refusals_5.json`, one per PRD category.  Pregnancy (case 3) and surgery (case 2) are covered.  Target:  4 hand-offs and 1 clarifying question (case 4, the ambiguous symptom).  Next:  run them live, then each of you grades the other's notes.
3. **Survey.**  Not run.  The counts go into PRD Section 1.
4. **Time model.**  3 seconds per rep, the rest given after every set, 30 seconds between exercises.  Still an assumption:  no workout has been timed with a stopwatch, so the constants are unchanged.  On 2026-10-14 the prompt (step 7) was changed to aim within 2 minutes (`AIM_MINUTES`) while the pass band stays 5; across 13 live plans every total landed within 1.1 minutes of the request (before:  21 plans from -3.0 to +4.8).  PRD 3b step 7 was updated to match on 2026-10-14 (Yadan agreed on 2026-10-14).  Open question for a stopwatch trial:  counting a rest after the last set of an exercise on top of the 30-second transition may over-count (about 1 minute per exercise at 60 seconds of rest).  Timed moves such as planks are version 2.
5. **Fixed wording for the no-plan messages.**  Drafted in `docs/fixed-messages.md` and already used by the code and prompt; **PRD Section 3b still has the looser v0 wording**.  Agree it, then update the Google Doc.  Includes a 10 to 45 minute range.
6. **Blue items in diagram v3 (proposed, not in the PRD).**  This repo already keeps only English name, equipment, muscles, and category (descriptions are dropped; `include_description=True` brings them back), drops exercises that need gear the user lacks, marks the cut, and drops exercise names that are sentences or longer than 45 characters (an injection filter).  Confirm or remove.
7. **Visible-error wording.**  `ERROR_MESSAGE` and `BUDGET_MESSAGE` in `harness.py` are placeholders.
8. **Missing "(assumed)" marker (agent miss, request set A case a15).**  "I have 20 minutes.  Arms." produced "20 min, nothing, arms" with no "(assumed)", although the user did not state equipment.  A repeat on 2026-10-14 (5 runs, saved as `runs/20261014-141908-assumed_marker_diagnosis.json`) dropped it once more, so a15 has missed 2 of 6 runs.  Two siblings and two controls behaved as expected in all 20 runs (siblings showed the marker 5 of 5; controls showed none).  The marker is intermittent:  "nothing" appears in the runs with and without it, so the "nothing is read as stated" idea is not supported.  Only the prompt enforces it.  A reworded step 3 (tried 2026-10-14, not committed; saved as `runs/20261014-143001-assumed_marker_fixcheck.json`) cut the misses to 1 of 20 a15 runs, with sib2 5 of 5 and both controls 0 of 5, but missed the 20-of-20 bar.  A prompt alone cannot meet it, so on 2026-10-14 the marker moved into code (`homeset/assumed.py`, wired into the harness before the output checks).  36 model-free tests pass, including all 20 request-set A inputs.  Still open:  re-run a15 live to confirm, and match PRD 3b (step 3 and the output-format line) with Yadan's confirmation.  The case stays as written.