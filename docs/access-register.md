# HomeSet access register

Draft 2026-10-19.  One row per grant.  A grant with no row has no reason to stay.  The **Enforced by** column says where each limit lives; a limit that lives only in the prompt is marked **prompt only** and counts as a gap.

**Who can trigger HomeSet:**  the person at the terminal.  There is no server, schedule, webhook, or inbound channel, and no accounts or roles (version 2).
**Untrusted text that reaches the model:**  the user's message; exercise names from wger (filtered); the saved plan file (validated).
**Owner:**  Valerie.  **Review by:**  2026-11-02 (proposed), or sooner at any trigger listed at the end.

## Grants

| Grant | Job step that needs it | Breaks without it | Enforced by (where the limit lives) | Verified by |
|---|---|---|---|---|
| **Anthropic key** (`ANTHROPIC_API_KEY`, personal, issued by Pursuit) | Every model call that writes a plan | No plans from the model; the code-only paths (hand-off, vague-symptom question, fixed refusals) still answer | `.env` is mode 600, git-ignored, and not tracked; `agent.py` reads it once and passes it to the model client; the model has no tool that reads the environment or any file | Checked 2026-10-19 with `ls -l` and `git ls-files`; **no automated test** |
| **`search_exercises`** (read from the public wger service; no wger key) | Find exercises for the focus and equipment | No plan; the tool returns an error the model must report | The model sends only a focus label and equipment labels; `labels.py` maps them to wger IDs and raises `UnknownLabel` for anything else, so free text never reaches the URL; fixed `BASE_URL`; GET only; a `next` link to another host is not followed; only the cleaned name and tags survive; a name filter drops instruction-like names; 30 s cap per search | `tests/test_guarantees.py` (4 tests); `tests/test_wger.py` |
| **`calculate_plan_time`** (pure arithmetic) | Total minutes for a plan | The model would do the time math itself | No network, no files; shares the cap below | `tests/test_plan_time.py` |
| **Tool-call and list caps** (10 calls per request, 1 regeneration; lists of at most 20 items) | Keeps one request from looping and one call from carrying a huge list | Not a grant; it limits the two tools above | `MAX_TOOL_CALLS` in `harness.py`; the 11th call returns `tool_call_limit`.  `MAX_LIST_ITEMS` (20, added 2026-10-19): an `equipment` or `exercises` argument that is not a list, or is longer than 20, returns `bad_list`, still counts as a call, and is traced as its first 20 items plus a marker.  Live runs sent at most 2 equipment labels and 6 exercises in 290 calls | `tests/test_harness.py`; `tests/test_guarantees.py` (9 tests, bar written first) |
| **Saved plan write** (`saved_plan.json`) | Save a plan and swap in a later session | No saved plan; every session starts fresh | **The model has no tool for it:**  `agent.py` and `harness.py` never import `saved_plan`.  `write()` refuses without an `Approval` for the same hash; the approval comes only from the exact answer "yes" at a terminal; the write is atomic and owner-only.  On read, a link, another owner's file, a file others can change, a file over 32 KB, or an odd `saved_at` is ignored with a reason | `test_the_model_side_modules_never_import_the_write`; the `test_write_refuses_*` tests; break-it B3 to B7 |
| **Run logs** (`runs/`) | Eval results and traces for debugging | Evals still run; nothing is saved for later reading | Git-ignored (`.gitignore` line 7).  On this machine `runs/` was mode 755 and the files 644; fixed 2026-10-19 (folder 700, files 600).  The 700 folder blocks other local users even when a new run file is created as 644 | `git check-ignore`; permissions checked 2026-10-19 before and after the fix |
| **Repo write access** (Yadan, collaborator on `valerie-zandoli/homeset`, public) | Pair work on the code | Yadan cannot push | GitHub collaborator setting, outside the code; from the 2026-10-14 invite, not re-checked | Not tested |

## Withheld on purpose

Shell, file, and network tools for the model (beyond wger); email, calendar, and Slack; any database; any wger account or key (HomeSet only reads); any path from the model to the saved-plan write; accounts, roles, and a separate approver (version 2).

## Enforcement gaps (fix, accept, or decide)

1. **Fixed 2026-10-19:  `runs/` was readable by other local users.**  The folder is now mode 700 and the files 600; the files hold request text.  Repeat on any new machine, because a fresh clone creates `runs/` with default permissions.
2. **Fixed 2026-10-19:  the model's tool list is pinned to exactly two tools.**  An earlier test counted what `make_tools` returns, so a tool added inside `build_agent` would have passed.  `test_the_agent_registers_exactly_the_two_named_tools` now reads the tools the Agent registers; a third tool fails the test (checked by adding a `read_file` tool, then reverting) and needs a new row here.
3. **`.env` mode is checked by hand only.**  Optional:  warn at startup when the mode is not 600.
4. **A demo machine holds a copy of the key.**  Decide when to delete it and whether to ask Pursuit to rotate the key after the 2026-10-19 demo.
5. **The owner check is skipped on Windows**, so a saved plan there loads without it.
6. **`Approval` stops a mistake, not a hostile Python caller.**  The guarantee is that the model has no tool for the write.
7. **Not visible from here:**  any spending cap or scope on the Pursuit-issued key.

## Review triggers (review at once, not on the date)

A new tool; a new input source (files, web pages, other users); accounts or a separate approver; a second user or a server deployment; any request to let the model write a file or send a message.  Each change adds a row above and a new review date.
