# Fixed wording for messages with no plan (DRAFT, 2026-10-13)

For Valerie and Yadan to agree.  The code (`homeset/messages.py`) and the prompt
(`homeset/prompt.py`) use this wording; **PRD Section 3b still has the looser v0 wording**
for rows 2 and 3, so update the Google Doc only after you both agree.

Why fixed wording:  these messages go straight to the user without the plan checks, so the
harness has to recognize them.  A fixed opening sentence makes that a string match.

| # | When | Exact message (slots in angle brackets) | Kind |
|---|---|---|---|
| 1 | wger cannot be reached after one retry | I could not reach the exercise database.  Would you like me to try once more? | error |
| 2 | the search returns no exercises | I could not find any exercises for \<focus\> with \<equipment\>.  Would you like to try a different focus or add equipment? | question |
| 3 | too few exercises for the time | I found only \<n\> exercises for \<focus\> with \<equipment\>, which is not enough for \<minutes\> minutes.  Would you like a shorter workout of about \<shorter\> minutes? | question |
| 4 | minutes outside 10 to 45 (for example "2-minute full-body workout") | I plan workouts of 10 to 45 minutes, and \<n\> minutes is outside that range.  How many minutes do you have, between 10 and 45? | question |
| 5 | minutes missing | How many minutes do you have? | question |
| 6 | no label fits the user's words | I am not sure which \<focus or equipment\> you mean.  Which of these fits best: \<the closest labels\>? | question |
| 7 | pain, injury, surgery, pregnancy, or a medical condition | I cannot plan workouts around pain, injuries, or medical conditions.  Please talk to a doctor or physical therapist first. | handoff (unchanged from the PRD) |

Decisions this needs from you:

1. **The range.**  10 to 45 minutes comes from the PRD's primary user (Section 1b).  A user who asks for 60 minutes gets row 4.  Widen it if you prefer.
2. **Question marks.**  Rows 2 to 6 end with a question, so the harness treats them as a question and skips the plan checks.  A plan can never be mistaken for one:  every plan starts with "HomeSet plan:".
3. **Who enforces the range.**  Today the model does (prompt step 3).  Code could do it before the model call, but the safety check must still come first, so it is not done.
4. **Visible errors from the harness** (`ERROR_MESSAGE`, `BUDGET_MESSAGE` in `harness.py`) are separate placeholders and still need wording.
