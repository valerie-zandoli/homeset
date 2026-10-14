# Regression log

Rule:  a failure found in a live run, a review, or a demo gets a row here and a unit test or an eval case **in the same commit as the fix**.  A case that spans the model also gets a live case in `evals/cases/regressions.json`.  Nothing merges while a row's test fails.

| Found | Symptom | Cause | Fix | Unit test | Live case |
|---|---|---|---|---|---|
| 2026-10-13, first live Eval Card run | A plan with names such as "Pike Hold (Floor)" failed the name check | The plan parser stopped reading a name at the parenthesis | `bbad512` | `tests/test_checks.py::test_names_with_parentheses_are_read_from_the_known_names`, `::test_an_unknown_name_with_parentheses_is_reported_by_name` | `reg_parentheses_in_names` |
| 2026-10-13, drafting the 20 test requests | "Give me a 20-minute workout" got a question about time instead of a plan | The hyphenated form was not read as minutes | `e87c879` | `tests/test_harness.py::test_extract_minutes` | `reg_hyphenated_minutes` |
| 2026-10-13, first live injection run | The tool-borne injection case never injected | The runner changed the parsed result, not the raw page, so names were cleaned before the poison reached them | `7207130` | `evals/cases/eval_card.json` cases `extra_tool_borne_injection` and `extra_tool_borne_injection_all` | same |
| 2026-10-13, review of the diagram | Sentence-like exercise names reached the model | No check on the name before it entered the prompt | `bcd2b23`; cap lowered from 60 to 45 in `150a05d` | `tests/test_wger.py::test_a_name_that_is_a_sentence_is_dropped`, `::test_a_long_name_or_a_name_with_a_line_break_is_dropped` | `extra_tool_borne_injection_all` |
| 2026-10-13, direct guarantee tests | A response could send the client to another host through its `next` link | The client followed any `next` URL | `a1d2f72` | `tests/test_guarantees.py::test_a_next_link_to_another_host_is_not_followed` | none (code only) |

## Known gap, not fixed

`equipment` and `muscles` names are passed to the model exactly as wger sends them.  They come from small admin-curated tables, not community edits, so the risk is low.  The stronger fix is to show the model our own label for each ID.  Revisit if wger lets users edit those tables.
