# HomeSet presentation script (final, 2026-10-19)

Cycle 2 story:  the role, the loop, a live demo, what broke and what we fixed, what is next.  Hard cap:  4 minutes for the pair.  Valerie types the demo on her machine; Yadan narrates it.  Yadan's lines stay in his voice.

Built from Yadan's draft of 2026-10-19 (14:58 ET) with four edits that Valerie sent him at 15:08 ET:  the hand-raise lines and the TRX story are cut to fit the cap;  the "rule into code" line, the totals line, and the "what is next" line now match the repo.

## Timing

| Part | Speaker | Seconds |
|---|---|---|
| Showcase opener (plays by itself, ends on the title card) | none | 30 |
| Hook | Valerie | 5 |
| Role | Valerie | 20 |
| The loop | Yadan | 35 |
| Live demo | Valerie types, Yadan narrates | 75 |
| What broke and what we fixed | Valerie | 35 |
| What is next | Yadan | 25 |
| Close | both | 5 |
| **Total** | | **230 (3:50)** |

Cut order if over:  1. the advanced-moves story;  2. the last sentence of "what is next";  3. the last 10 seconds of the showcase.

## Before you start

1. Close every window that shows `.env` or a key.  Turn on Do Not Disturb.
2. Open one terminal tab in the `homeset` folder with `.venv` active, and clear the scratch saved plan:  `export HOMESET_SAVED_PLAN=/tmp/homeset_demo_plan.json`, then `rm -f /tmp/homeset_demo_plan.json`.
3. Open the showcase:  `python -m homeset.web`, then `http://127.0.0.1:8000/showcase` (or open `homeset/showcase.html` from the file).  Click once for full screen.
4. Keep `python scripts/try_checkpoint.py` ready on Yadan's machine as the backup (no key, real Terminal window).

## Script

**[OPENER, about 30 seconds, no speaking]**  The showcase plays and ends on "HomeSet.  One sentence in.  One plan out."

**[HOOK, Valerie, about 5 seconds]**
VALERIE: So we built HomeSet.  One sentence in.  One plan out.

**[ROLE, Valerie, about 20 seconds]**
VALERIE: HomeSet does one job:  it plans your workout at home.  Tell it your minutes, your gear, and what you want to work on.  It builds a numbered plan from real exercises in wger, a free exercise database, and that is the only database it is allowed to use.

**[THE LOOP, Yadan, about 35 seconds]**
YADAN: Here's what's happening behind the screen.  The AI reads your request and picks labels, like "legs" and "mat."  Then our code takes over:  it searches wger and does every bit of the time math.  The AI never guesses a number.
YADAN: And before you see a single exercise, the plan has to pass eight checks.  Real exercises.  Gear you actually own.  Time on target.  Nothing too advanced for a beginner.  And a safety line, every time.
YADAN: Our one rule:  the AI makes the judgment calls;  the code enforces the rules.

**[LIVE DEMO, Valerie types, Yadan narrates, about 75 seconds]**
Step 1.  Valerie types:  `python -m homeset "I have 15 minutes and a mat.  Legs." --save`
VALERIE: Let's run it live.  "I have 15 minutes and a mat.  Legs."
YADAN (while it runs, about 20 seconds): Right now it's pulling real exercises from wger, building the plan, and running all eight checks.  If any check fails, you never see that plan.
YADAN (plan appears): About fifteen minutes, five exercises, total time calculated by code.
YADAN: Now our new feature:  saving.  Saving replaces your old plan, so HomeSet asks first.  It shows your saved plan next to the new one, and only a "yes" saves it.
VALERIE: [types yes] Saved.

Step 2.  Valerie types:  `python -m homeset "Swap the first exercise." --saved`
YADAN: Tomorrow you come back:  "Swap the first exercise."  [about 12 seconds]  Same plan, exactly one exercise changed, nothing else touched.

Step 3.  Valerie types:  `python -m homeset "My knee hurts.  I have 15 minutes and a mat.  Legs." --trace`
VALERIE: Now the most important one:  "My knee hurts."
YADAN (about 1 second): Instant.  No plan, no exercises, just:  talk to a doctor or physical therapist.  The trace shows the AI was never even called.  Our code caught it first.  Safety is not something we ask the AI to do;  it is built in.

If a step fails:  try once, then run `python scripts/try_checkpoint.py` on Yadan's machine (`yes`, then `no`) and say in one sentence what failed.

**[WHAT BROKE AND WHAT WE FIXED, Valerie, about 35 seconds]**
VALERIE: Testing humbled us fast.  Here is what broke, and what we did about it.
VALERIE: Beginners got pull-ups.  Now advanced moves are blocked before the AI sees them, and checked again after.
VALERIE: Workout totals swung from 3 minutes short to almost 5 over.  Now all 20 of our test requests land within 1.5 minutes.
VALERIE: When a rule must always hold, we moved it into code.  The AI dropped one required marker in 3 of 26 runs.  Code now writes it, and it passed 5 of 5.

**[WHAT IS NEXT, Yadan, about 25 seconds]**
YADAN: What's next:  our time model is still an estimate, so we will time real workouts with a stopwatch, and we will survey 8 to 10 people to make sure we are solving the right problem.  And the chat you saw at the start is where we are headed, so it feels less like a terminal and more like texting a coach.

**[CLOSE, both, about 5 seconds]**
VALERIE: HomeSet.  One sentence in...
YADAN: ...one plan out.  Thank you!

## Facts behind the numbers (for questions)

| Claim | Source |
|---|---|
| Eight output checks | `homeset/checks.py`; `docs/architecture-v4.png` |
| The AI dropped the "(assumed)" marker in 3 of 26 runs; code then passed 5 of 5 | README Open item 8;  `runs/20261014-145550-assumed_marker_code_a15.json` |
| Totals from 3.0 minutes short to 4.8 over, 21 plans | `homeset/plan_time.py` docstring (2026-10-13 and 2026-10-14 runs) |
| All 20 requests within 1.5 minutes (gaps -1.1 to +1.5) | `runs/20261019-015811-requests_20.json` |
| Advanced moves blocked before and after the model | `homeset/advanced.py`;  `docs/architecture-v4.png` |
| The trace line "the model is not called" | `--trace`;  `homeset/triggers.py` |
| Save needs a typed "yes" at a terminal, or a click on the chat page | `homeset/saved_plan.py`;  `docs/access-register.md` |
| The time model, a stopwatch trial, and the survey are not done yet | README Open item 4 (time model) and Open item 3 (survey, "Not run") |
