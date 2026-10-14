# HomeSet pitch script (draft v2, 2026-10-14)

Design pitch for Monday, 19 October 2026.  Hard cap:  4 minutes for the pair.  This is a design pitch, not a product demo.

Based on Yadan's script of 2026-10-13 (8 slides, Valerie on 1, 2, 3, 6, 7 and Yadan on 4, 5, 8).  Changed lines are marked **[changed]**; new content is marked **[new]**.  Yadan's lines stay in his voice.

## Timing

| Item | Value |
|---|---|
| Spoken words, without the "cut first" paragraph | about 458 (script 443 plus about 15 for your personal reason), which is 3:03 at 150 words per minute and 3:31 at 130; add about 10 seconds for the three hand-offs.  Not yet timed with a stopwatch. |
| Target | under 3 minutes 45 seconds; hard cap 4 minutes |
| Stopwatch time | Run one rehearsal and write the measured time here:  ______ |
| Cut order if over | 1. slide 6, "cut first" paragraph.  2. slide 7, the second sentence.  3. slide 5, the last two sentences. |

## Script

### 1.  HomeSet  (Valerie)  [changed]

On screen:  big "HomeSet" title, our names, and one line:  "Consumer fitness · workout planning".

Hi everyone!  We are Valerie and Yadan, and our agent is HomeSet.  We chose consumer fitness, and within it workout planning, the work a trainer does when writing one session.  Many people try fitness apps and drop them, and one session is a small, safe job for an agent.  [Valerie:  add one sentence with your personal reason for choosing fitness.]

▶ Click

### 2.  The problem  (Valerie)

On screen:  big orange "1 in 4".

Here is the problem.  People want to work out at home, but with only 20 or 30 minutes, deciding what to do takes too much energy, so they skip it or repeat the same few moves.  Only about 1 in 4 US adults meet both federal exercise guidelines.

▶ Click

### 3.  What HomeSet does  (Valerie)  [changed]

On screen:  "You type" → "You get", plus three promises from the PRD.

HomeSet fixes that.  You type one sentence, such as "I have 20 minutes, a mat, and dumbbells.  Work on legs," and you get a numbered workout plan.  Our PRD, the product requirements document, promises three things:  built for busy adults at home; every exercise from the free wger database; and a total within 5 minutes of your time.

▶ Click, hand off to Yadan

### 4.  How it works  (Yadan)  [changed: one phrase]

On screen:  4 steps, 1 to 4.

Here's how it works.  You send your request, the AI picks labels for your equipment and focus, our code turns those labels into database filters and looks up the exercises, and you get a plan that is checked before you see it.  The AI makes the judgment calls, and the code enforces the rules.

▶ Click

### 5.  System prompt and safety  (Yadan)  [new: the system prompt; shortened]

On screen:  three safeguards on top, two boxes below.

The biggest risk is safety, so our system prompt gives the agent one role:  a workout planner, not a doctor.  It checks for safety first:  if you mention pain, an injury, surgery, or pregnancy, it gives one fixed sentence and sends you to a doctor or physical therapist.  It names only exercises from the database.  We also marked two places someone could try to trick it:  your message, and the database text.  The hardest call is "I'm sore from yesterday" versus "my knee hurts," so that is where most of our tests focus.

▶ Click, hand off to Valerie

### 6.  Why we believe it will work  (Valerie)  [new]

On screen:  the test table, and the line "Rules that must always hold are in code."

Why do we believe it will work?  The rules that must always hold are in code, not in the prompt.  We watched the prompt fail:  the model dropped one required marker in 3 of 26 runs, so we moved it into code, and it then passed 5 of 5.  Every plan landed within 5 minutes of the request, and all 5 refusal cases gave the safe reply:  4 hand-offs and 1 question.

**Cut first:**  Testing also caught two bugs.  The database sends 20 results at a time, which our code now pages through, and refusals now go straight to the user.

▶ Click

### 7.  The full design  (Valerie)

On screen:  the detailed diagram.  Replace the "Red box" and "Left arrow" callouts with numbered markers or two zoomed crops, so each callout points at something.

This is the full design, and it is in our PRD.  The red box is the paging fix, and the left arrow is the path that sends refusals straight to the user.

▶ Click, hand off to Yadan

### 8.  What is next  (Yadan)  [changed: "full thing"]

On screen:  three next steps, "Thank you!"

Next, we're surveying 8 to 10 people to check we're solving the right problem, and we'll time real workouts with a stopwatch.  Then we'll finish the build and score it on accuracy, reliability, and safety.

**Both:**  Thank you!

## Facts behind slide 6 (for questions)

| Claim | Source |
|---|---|
| The model dropped the "(assumed)" marker in 3 of 26 runs | README Open item 8:  1 of 1 first run, 1 of 5 repeat, 1 of 20 after the prompt reword |
| After the move to code, 5 of 5 | `runs/20261014-145550-assumed_marker_code_a15.json`; 36 tests in `tests/test_assumed.py` cover all 20 request-set A inputs |
| Every plan within 5 minutes | Request set A:  20 of 20 plans, largest gap 1.6 minutes (`runs/20261014-132821-requests_20.json`) |
| 5 refusal cases, 4 hand-offs and 1 question | `runs/20261014-145559-refusals_5.json`; target in `evals/cases/refusals_5.json` |
| Known limit, if asked | The marker rule reads the user's words against a fixed word list, so an unusual equipment word gets a harmless "(assumed)" (`homeset/assumed.py`) |

## Deck edits for Yadan

1. Slide 1:  add "Consumer fitness · workout planning".
2. Slide 3:  list the three PRD promises.
3. Slide 5:  title it "System prompt and safety".
4. Slide 6:  replace "5 of 5 refusal cases" with "all 5 refusal cases gave the safe reply (4 hand-offs, 1 question)", and add the code-versus-prompt line.
5. Slide 7:  numbered markers or zoomed crops in place of "Red box" and "Left arrow".

## Rehearsal

1. Read it aloud once with a stopwatch, both speakers, with the clicks.
2. Write the time at the top.  Over 3:45, cut in the order above.
3. Rehearse twice before Monday; each of you should be able to explain any slide.
