# PLAN — `claude -p` backend for job-applicator

## Orchestrator protocol

- You coordinate; you do not implement. Do not read large files or run long commands yourself. Delegate them.
- Loop: pick the next task whose dependencies are all DONE → spawn the named agent type with "Shared context" + the task brief, verbatim → read the report → spawn `plan-verifier` with the brief and the report → update this plan → next task. A task is DONE only on a PASS verdict; a FAIL counts as a failed task (see below).
- Tasks with no dependency on each other and no shared files may run in parallel.
- Only you edit this file. Subagents never edit it.
- On BLOCKED, FAILED or a verifier FAIL: retry at most once with a corrected brief. If it fails again, stop and ask the user.
- After every task, update the status table and append to the Progress log. A fresh session must be able to resume from this file alone.

## Goal, non-goals, constraints

**Goal.** Let every LLM call in the pipeline run through `claude -p` (headless Claude Code) so it draws on Hugo's Claude Code subscription instead of the Anthropic API. Choose the backend with a new `apply.py` flag `--backend {api,cli}`, default `cli`. `--backend api` keeps today's behaviour exactly.

**Non-goals.**
- No changes to prompts in `prompts/` or to the stage modules `analyse.py`, `report.py`, `adapt.py`, `verify.py`, apart from what the brief explicitly allows. The backend switch lives in `stages/_client.py`.
- No use of the subscription's OAuth token outside the `claude` CLI (no Agent SDK, no direct API calls with that token).
- No retry or backoff logic for the CLI backend.
- No git commits or pushes. Hugo commits.
- No new packages.

**Constraints.**
- Work only inside `/home/hugo/code-projects/job-applicator`. Do not read or write outside it, except to run the `claude` binary.
- Never print, log or commit `ANTHROPIC_API_KEY` or the contents of `.env`.
- `CV/`, `CL/`, `preferences.md`, `notices/` and `output/` hold personal data. Read them only where a brief says so. Never write into an existing `output/<slug>/`.
- Live `claude -p` calls use Hugo's subscription quota. Only T1 (about 5–10 short Sonnet calls) and T3 (one analyse plus one Opus adapt) may make them.
- At the end, the orchestrator asks Hugo before deleting `PLAN-cli-backend-spike.md`, `PLAN-cli-backend-smoke.md` and `output/_cli-smoke/`. Never delete them without asking.

## Shared context

- Repo: `/home/hugo/code-projects/job-applicator`. Python CLI: `apply.py` (argparse, `main()` calls `load_dotenv()`, which puts `ANTHROPIC_API_KEY` from `.env` into `os.environ`).
- Activate the venv first in every shell: `source .venv/bin/activate`. Never `pip install`.
- Lint: `ruff check .`. Tests: `python -m unittest discover -s tests`. Both must be clean before a task counts as done.
- All LLM calls go through `stages/_client.py`:
  - `call_with_cache(*, model, max_tokens, prompt, tools=None, tool_choice=None, stage_label)`. The prompt holds `===CACHE_BREAKPOINT===`, which `split_at_breakpoint()` splits into a cached prefix and a variable suffix.
  - `call_simple(*, model, max_tokens, prompt, stage_label)`.
  - `estimate_tokens(text)` calls the API `count_tokens` endpoint and falls back to `_heuristic_tokens` (chars/4).
  - Both call functions return an Anthropic `Message`. Callers read `.content` (blocks with `.type == "text"` and `.text`, or `.type == "tool_use"` with `.name` and `.input`), `.stop_reason` (`"max_tokens"` triggers a warning) and `.usage` (via `_log_usage`).
- Callers:
  - `stages/analyse.py` and `stages/batch.py:quick_scan` pass a single strict tool (`ANALYSIS_TOOL`, `SCAN_TOOL`, each with `input_schema`) and `tool_choice={"type": "auto"}`, then read the `tool_use` block.
  - `stages/report.py`, `stages/adapt.py`, `stages/verify.py` and `stages/batch.py:extract_job_urls` read text through `extract_text()`.
- Models: `claude-sonnet-5-5` (analyse, batch scan, verify, URL classifier) and `claude-opus-5-5` (report, adapt; `max_tokens=16384`).
- Batch: `stages/batch.py:scan_all(..., max_workers=MAX_SCAN_WORKERS)` with `MAX_SCAN_WORKERS = 3` uses a `ThreadPoolExecutor`. `stages/orchestrate.py:163` calls `scan_all(sources, cv_tex)` with no `max_workers`.
- Tests: `tests/test_stages.py` patches `stages._client._client` with a `_FakeClient` (`_patch_client`, `_mk_message`, `_text_block`, `_tool_block`). Leave those tests as they are.
- Code style (from `CLAUDE.md`): no comments unless the *why* is non-obvious; type-annotate signatures; no error handling for impossible cases; never swallow errors silently; touch only what the task needs.
- `claude --help` is the reference for CLI flags. Known facts:
  - `-p/--print`, `--output-format json`, `--json-schema <schema>`, `--model`, `--system-prompt`, `--tools`/`--allowedTools`/`--disallowedTools` and `--max-budget-usd` exist.
  - `--bare` can NOT be used: it reads auth only from `ANTHROPIC_API_KEY` and never uses OAuth.
  - If `ANTHROPIC_API_KEY` is in the child's environment, Claude Code may bill the API instead of the subscription.

## Decisions made

1. **The switch lives only in `stages/_client.py`.** The CLI backend returns a `types.SimpleNamespace` shaped like an Anthropic `Message` (`content`, `stop_reason`, and `usage` with `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`). This leaves every caller unchanged. *Reason:* smallest blast radius; callers already handle this shape.
2. **Tool calls map to `--json-schema`.** When `tools` is passed (always exactly one tool), its `input_schema` goes to `--json-schema` as JSON, and the parsed structured output becomes `SimpleNamespace(type="tool_use", name=tools[0]["name"], input=<dict>)`. `tool_choice` is ignored under `cli`. *Reason:* `--json-schema` enforces the schema, as strict tools do on the API.
3. **Backend selection.** `_client.py` has a module variable `_BACKEND` (default `"api"`) and a function `set_backend(name: str) -> None` that accepts `"api"` or `"cli"`. `apply.py` adds `--backend {api,cli}` (default `cli`) and calls `set_backend(args.backend)` right after parsing. *Reason:* the CLI default matches Hugo's choice, while library-level calls and the existing mocked tests keep the API path.
4. **Key stripping.** Under `cli`, the subprocess always runs with `ANTHROPIC_API_KEY` removed from a copy of `os.environ`. *Reason:* `load_dotenv()` would otherwise send calls to API billing without anyone noticing.
5. **Prompt caching.** Under `cli`, the prompt is still checked with `split_at_breakpoint()` and then sent as `prefix + "\n\n" + suffix`. Cache control is left to Claude Code.
6. **Token estimates.** Under `cli`, `estimate_tokens` returns `_heuristic_tokens(text)` directly, without calling `count_tokens`, because that endpoint needs an API key.
7. **Batch.** Under `cli`, batch keeps working but with fewer workers. Add `CLI_MAX_SCAN_WORKERS` in `stages/batch.py`, at most 2, with the exact value set by T2 from T1's findings. `scan_all`'s `max_workers` defaults to `None`, which resolves to the right constant for the active backend. *Reason:* each `claude -p` call is a full process with startup cost and uses subscription quota.
8. **Errors.** Under `cli`, these raise `RuntimeError` with the stage label and a short excerpt of the output (never env vars): a missing `claude` binary (with a hint to use `--backend api`), a non-zero exit code, an `is_error`-style result, or missing structured output when a schema was given. A subprocess timeout raises as well. There is no retry.
9. **Output length.** `max_tokens` is passed to the CLI the way T1 finds works (expected: the `CLAUDE_CODE_MAX_OUTPUT_TOKENS` environment variable). If T1 finds no way to do this, T2 documents the gap in `CLAUDE.md` rather than inventing one.
10. **Smoke-test outputs** go to `output/_cli-smoke/`. It is gitignored like the rest of `output/` and is not a real vacancy slug.
11. **Isolation flags** (added after T1, approved by Hugo 2026-11-17). The argv includes `--safe-mode --strict-mcp-config`, together with `--system-prompt` and `--tools ""`. *Reason:* without `--safe-mode`, the CLAUDE.md files, memory, MCP tools and the account email leak into the child context.
12. **Output cap** (added after T1, approved by Hugo 2026-11-17). `max_tokens` is passed as `CLAUDE_CODE_MAX_OUTPUT_TOKENS`. When the cap is hit, the CLI returns no partial text (`is_error: true`, `api_error: "max_output_tokens"`, exit 1). Under `cli` this raises a `RuntimeError` that names the stage and says the `max_tokens` cap was hit. The `stop_reason == "max_tokens"` warning path is therefore API-only. This replaces the truncation clause in Decision 9 and in T2 step 1.
13. **Default stays `cli`** even though the account is on Pro, not Max (Hugo, 2026-11-17).

## Task table

| ID | Title | Agent type | Depends on | Files touched | Status |
|---|---|---|---|---|---|
| T1 | Probe `claude -p` with live calls and record findings | `coder` | — | `PLAN-cli-backend-spike.md` (new) | DONE |
| T2 | Implement the CLI backend, `--backend` flag, batch worker cap, tests and docs | `coder` | T1 | `stages/_client.py`, `apply.py`, `stages/batch.py`, `tests/test_client_cli.py` (new), `CLAUDE.md`, `README.md`, `.claude/skills/job-applicator/SKILL.md` (only if needed) | DONE |
| T3 | Live smoke test of `analyse` and `adapt_cv` under `cli` | `coder` | T2 | `PLAN-cli-backend-smoke.md` (new), `output/_cli-smoke/` (new) | DONE |
| T4 | Final verification | `plan-verifier` | T3 | none | DONE |

## Task briefs

### T1 — Probe `claude -p` and record findings

**Objective.** Answer, with evidence from real runs, the questions T2 needs to build the CLI backend, and write the answers to `PLAN-cli-backend-spike.md`.

**Inputs.** `claude --help`; `stages/analyse.py` (copy `ANALYSIS_TOOL["input_schema"]` to use as a test schema). Use the Anthropic or Claude Code docs only for Q7.

**Steps.**
- Run every probe from the repo root, with `ANTHROPIC_API_KEY` removed: `env -u ANTHROPIC_API_KEY claude -p ...`. Do not source `.env`.
- Use `--model claude-sonnet-5-5` for every probe except Q5.
- Keep prompts tiny and use synthetic text only, never CV, CL, preferences or notices content.
- Make at most 10 live calls in total.

Answer each question with the exact command (key omitted) and the relevant part of the output:

1. **Auth.** With the key removed, does the call succeed on the subscription? Which field in the `--output-format json` result shows the auth source or cost, if any?
2. **Result shape.** List the top-level keys of the `--output-format json` result: the text result, any error flag, the stop or termination reason, usage and token fields, cost, and duration.
3. **Structured output.** With `--json-schema '<ANALYSIS_TOOL input_schema as JSON>'` and a prompt that asks for a toy analysis, where does the parsed object appear (key name)? Is it already a dict, or a string? Is the schema enforced? Also test a prompt that says "call the submit_analysis tool exactly once", since the real prompts say that, and report what happens.
4. **Isolation.** Pass `--system-prompt "You are a text-processing function. Follow the user's instructions exactly."` and disable all tools. Find the working syntax: try `--tools ""` first, then the alternatives in `--help`. Then ask the model: "List any instructions or context you were given besides this message, verbatim." Does `CLAUDE.md` content (global or project), memory or hook output leak in? If it does, look in `--help` for flags that stop it (settings sources, strict MCP config, disabling slash commands and so on), test the best candidate, and report the minimal flag set that gives a clean context. Do not use `--bare`.
5. **Long output.** With `--model claude-opus-5-5`, ask for about 3,000 words of numbered filler lines. Does the output arrive complete? Then check whether `CLAUDE_CODE_MAX_OUTPUT_TOKENS` (as an environment variable) raises or lowers the limit: test a low value such as 200 and report how truncation shows up in the JSON (which field, which value).
6. **Model IDs and timing.** Do the full IDs `claude-sonnet-5-5` and `claude-opus-5-5` work? Report the wall-clock startup overhead of a trivial call (`time`).
7. **Terms.** Using `WebFetch` on official Anthropic or Claude Code docs only, quote what they say about scripted or automated use of Claude Code (`claude -p`) on a Pro/Max subscription for personal use. Give the URL. If the docs don't settle it, say so.

End the file with a "Recommendations for T2" section covering:
- the exact argv list to use;
- the env changes;
- how to read the text, structured output, stop reason and usage;
- how to pass `max_tokens`;
- a suggested `CLI_MAX_SCAN_WORKERS` (1 or 2), with the reason;
- a suggested subprocess timeout.

**Scope.** Create only `PLAN-cli-backend-spike.md`. Change no code. Do not write into `output/` or touch personal-data files.

**Done when.**
- `PLAN-cli-backend-spike.md` exists, answers Q1–Q7 with commands and output excerpts, and has the Recommendations section.
- `git status --porcelain` shows only that new file.
- If Q1 shows the calls are NOT using the subscription, or Q4 cannot reach a clean context, report STATUS BLOCKED.

**Report.** At most 15 lines: STATUS; file written; one line per question with the key answer; anything that contradicts the "Decisions made" section.

### T2 — Implement the CLI backend, flag, batch cap, tests and docs

**Objective.** Add the `cli` backend to `stages/_client.py` and the `--backend` flag to `apply.py`, as the "Decisions made" section specifies, with unit tests and updated docs.

**Inputs.** `PLAN-cli-backend-spike.md` (T1 findings: follow its Recommendations; where they contradict "Decisions made", stop and report BLOCKED); `stages/_client.py`; `apply.py`; `stages/batch.py`; `tests/test_stages.py` (for the existing fake-message style); `CLAUDE.md`; `README.md`; `.claude/skills/job-applicator/SKILL.md`.

**Steps.**
1. **`_client.py`.**
   - Add `_BACKEND = "api"` and `set_backend(name: str) -> None`, which raises `ValueError` for anything other than `"api"` or `"cli"`.
   - Add a private `_call_cli(*, model, max_tokens, prompt, schema, tool_name, stage_label)`. It builds the argv from T1, runs `subprocess.run` with a copy of `os.environ` minus `ANTHROPIC_API_KEY` (plus the output-limit variable if T1 confirmed it), the prompt on stdin, and the T1 timeout. It parses the JSON and returns the Message-shaped `SimpleNamespace` (Decision 1). It raises `RuntimeError` when the output cap is hit (Decision 12), sets `stop_reason="tool_use"` for schema results, and sets `"end_turn"` otherwise.
   - Route `call_with_cache` and `call_simple` to `_call_cli` when `_BACKEND == "cli"`. Keep the `max_tokens` warning and `_log_usage`.
   - Under `cli`, `estimate_tokens` returns the heuristic (Decision 6).
   - Errors follow Decision 8.
2. **`apply.py`.** Add `--backend` with choices `api` and `cli`, default `cli`, and help text noting that `cli` uses the Claude Code subscription through `claude -p`. Call `set_backend(args.backend)` right after `parse_args()`.
3. **`stages/batch.py`.** Add `CLI_MAX_SCAN_WORKERS` (value from T1, at most 2). `scan_all`'s `max_workers: int | None = None` resolves to that constant under `cli` and to `MAX_SCAN_WORKERS` otherwise. Read the backend through a small getter in `_client.py` (`get_backend() -> str`), not the private variable.
4. **`tests/test_client_cli.py`** (new, `unittest`, mock `subprocess.run` and never call the real CLI). Cover:
   - text result → `extract_text` works;
   - schema result → `tool_use` block with the right name and input, end to end through `analyse.analyse()`;
   - `ANTHROPIC_API_KEY` is absent from the env passed to `subprocess.run` even when it is set in `os.environ`;
   - the argv contains the model and the `--json-schema` only when tools are passed;
   - the argv contains `--safe-mode` and `--strict-mcp-config` (Decision 11);
   - an `api_error: "max_output_tokens"` result raises a `RuntimeError` that mentions `max_tokens` (Decision 12), and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` in the child env equals `str(max_tokens)`;
   - non-zero exit, error result and missing binary (`FileNotFoundError`) each raise `RuntimeError`;
   - `set_backend("bogus")` raises `ValueError`;
   - `estimate_tokens` makes no API call under `cli`;
   - `scan_all` uses `CLI_MAX_SCAN_WORKERS` under `cli`.
   Reset the backend to `"api"` in `tearDown`.
5. **Docs.**
   - `CLAUDE.md`: under Layout or Conventions, add one short paragraph on the two backends, the key stripping, the isolation flags, the hard-error behaviour at the output cap, and the risk from T1 Q7 that `--bare` may become the default for `-p` (which would break subscription auth). Add `python apply.py ... --backend api` to Commands.
   - `README.md`: document `--backend` and say the API key is only needed for `--backend api`.
   - `.claude/skills/job-applicator/SKILL.md`: change it only if it states something that is now false (for example, that an API key is required). Otherwise leave it alone.

**Scope.** Modify only the files in T2's row of the task table. Do not touch `prompts/`, `analyse.py`, `report.py`, `adapt.py`, `verify.py`, `orchestrate.py`, `tests/test_stages.py` or `tests/test_orchestrate.py`. Make no live `claude` calls.

**Done when.**
- `source .venv/bin/activate && ruff check . && python -m unittest discover -s tests` is fully clean, including all pre-existing tests unchanged.
- `python apply.py --help` lists `--backend {api,cli}`.
- `git diff --stat` shows only in-scope files.

**Report.** At most 15 lines: STATUS; files changed; test count and result; the chosen `CLI_MAX_SCAN_WORKERS` and timeout; how `max_tokens` is passed (or the documented gap); any deviation from T1's recommendations and why.

### T3 — Live smoke test under `cli`

**Objective.** Show that `analyse()` and `adapt_cv()` work end to end through the real `claude -p` backend, and record the evidence in `PLAN-cli-backend-smoke.md`.

**Inputs.** `PLAN-cli-backend-spike.md`; the T2 code. The vacancy text comes from one existing saved vacancy under `output/<slug>/`: list `output/`, pick any slug that has a saved vacancy text file, and read it without changing it. Load the CV and CL with `apply.find_tex` (or by reading the single `.tex` file in `CV/` and `CL/`), and load `preferences.md` if it exists.

**Steps.**
1. Write a throwaway script `output/_cli-smoke/run.py`. It calls `stages._client.set_backend("cli")`, runs `analyse.analyse(...)`, saves the result to `output/_cli-smoke/analysis.json`, then runs `adapt.adapt_cv(vacancy_text, analysis, cv_tex)` and saves the result to `output/_cli-smoke/cv_adapted.tex`.
2. Run it from the repo root with the venv active and the `--verbose`-equivalent DEBUG logging turned on (`stages.log`), so the usage lines appear. Leave `ANTHROPIC_API_KEY` in the parent environment on purpose, to show the stripping works. Time the run.
3. Check that:
   - `analysis.json` validates against `ANALYSIS_TOOL["input_schema"]` (all required keys present, `fit_score` in the enum);
   - `cv_adapted.tex` is complete, ending with `\end{document}` and showing no `max_tokens` warning in the log.
4. Write `PLAN-cli-backend-smoke.md` with:
   - the slug used;
   - the command;
   - wall-clock time per stage;
   - the usage log lines;
   - the validation results;
   - the evidence the subscription was used (the T1 Q1 field, if T1 found one);
   - any warnings.
   Do not paste CV, CL or vacancy content into this file.

**Scope.** Write only `output/_cli-smoke/*` and `PLAN-cli-backend-smoke.md`. Make no code changes in the repo. Do not write into any real `output/<slug>/`. Make exactly one analyse call and one adapt call: do not loop or retry.

**Done when.**
- Both artefacts exist; `analysis.json` passes the schema check; `cv_adapted.tex` ends with `\end{document}`.
- `PLAN-cli-backend-smoke.md` is written.
- `git status --porcelain` shows only `PLAN-cli-backend-smoke.md` as new, besides T1's file and T2's changes.

**Report.** At most 15 lines: STATUS; timings; schema-check and completeness results; subscription evidence; any problem T4 or Hugo should know about.

### T4 — Final verification

**Objective.** Confirm that the whole change meets the Goal, respects the non-goals, and leaves the suite clean.

**Inputs.** This plan file (Goal, non-goals, constraints, Decisions made); `PLAN-cli-backend-spike.md`; `PLAN-cli-backend-smoke.md`; `git diff` and `git status --porcelain`.

**Steps.**
1. Run `source .venv/bin/activate && ruff check . && python -m unittest discover -s tests`.
2. Check that `git diff --stat` touches only `stages/_client.py`, `apply.py`, `stages/batch.py`, `CLAUDE.md`, `README.md` and, optionally, `.claude/skills/job-applicator/SKILL.md`. The only new files should be `tests/test_client_cli.py`, `PLAN-cli-backend.md`, `PLAN-cli-backend-spike.md` and `PLAN-cli-backend-smoke.md` (`output/` is gitignored).
3. Check each of Decisions 1–10 against the code: one line per decision, PASS or FAIL with `file:line`.
4. Check the non-goals:
   - no edits to `prompts/` or to stage modules other than `batch.py`;
   - no Agent SDK or OAuth-token use;
   - no new dependencies in `requirements.txt` or `pyproject.toml`;
   - no commits made (`git log -1` is still `21ad4e4` or Hugo's own later commit);
   - no API key printed in any file (`grep -r "sk-ant" PLAN-cli-backend*.md tests/ stages/` is empty).
5. Confirm T3's smoke report shows a valid analysis and a complete adapted CV.

**Scope.** Read-only. Change nothing.

**Done when.** Lint and tests are clean, and every check in steps 2–5 passes.

**Report.** At most 15 lines: PASS or FAIL overall; test result; any failing decision or non-goal with `file:line`. After this, the orchestrator asks Hugo whether to delete `PLAN-cli-backend-spike.md`, `PLAN-cli-backend-smoke.md` and `output/_cli-smoke/`.

## Progress log

- 2026-11-17 T1 started. Ran as `general-purpose` instead of `coder`, because `coder` has no WebFetch and Q7 needs it.
- 2026-11-17 T1 DONE (verifier PASS). 10 live calls. Key findings: subscription works (Pro, not Max); structured output arrives in `structured_output` as a dict; a clean context needs `--safe-mode`; hitting `CLAUDE_CODE_MAX_OUTPUT_TOKENS` gives a hard error (`is_error`, `api_error: "max_output_tokens"`, exit 1, after 4 internal retries), not partial text; T1 recommends workers = 1 and a 600 s timeout. Two conflicts with Decisions (`--safe-mode`; truncation semantics) are waiting on Hugo before T2.
- 2026-11-17 Hugo approved Decisions 11–13. T2's brief has been amended to match (step 1 stop_reason, the step 4 tests, the step 5 CLAUDE.md paragraph). T2 started.
- 2026-11-17 T2 DONE (verifier PASS). 63 tests OK (16 new), ruff clean. CLI_MAX_SCAN_WORKERS = 1, timeout 600 s, max_tokens passed via CLAUDE_CODE_MAX_OUTPUT_TOKENS. The prompt goes on stdin, which T1 did not test live, so T3 is the first live check of it. SKILL.md is untouched. T3 started.
- 2026-11-17 T3 DONE (verifier PASS). Slug casp-regi. analyse 17.4 s, adapt_cv 40.5 s. The prompt on stdin works live. analysis.json passes the top-level schema check (fit_score Weak), and cv_adapted.tex ends with `\end{document}` with no max_tokens warning. `claude auth status` shows claude.ai/pro. Caching of large prefixes across calls is still unverified. T4 started.
- 2026-11-17 T4 PASS. Ruff clean, 63 tests OK, Decisions 1–13 all PASS against the code, non-goals respected, no commits (HEAD 21ad4e4). Remaining: ask Hugo whether to delete the spike and smoke files and output/_cli-smoke/.
- 2026-11-17 Hugo approved cleanup. Deleted PLAN-cli-backend-spike.md, PLAN-cli-backend-smoke.md and output/_cli-smoke/. Plan complete; nothing committed.
