# CLAUDE.md — job-applicator

Project-specific instructions for Claude Code. Read this first.

## What this is

Python CLI that ingests a vacancy (PDF or URL), runs a Claude-powered gap
analysis against the user's CV + cover letter, generates an interview-prep
report, and emits adapted CV/CL LaTeX files. Optional batch mode quick-scans
many vacancies in parallel.

User: Hugo, empirical economist. Personal CV/CL/preferences are gitignored.

## Layout

```
apply.py                 CLI entry: argparse + single-vacancy flow
stages/
  _client.py             Anthropic client wrapper, prompt-cache plumbing,
                         render_prompt, estimate_tokens, strip_code_fence
  ingest.py              Stage 1: PDF + URL → text (Playwright fallback)
  analyse.py             Stage 2: gap analysis (Sonnet, tool-use)
  report.py              Stage 3: interview-prep markdown (Opus)
  adapt.py               Stages 4-5: adapt CV + CL LaTeX (Opus)
  verify.py              Stage 6 (--verify): fabrication detector (Sonnet)
  batch.py               quick_scan + scan_all + ATS URL extraction
  orchestrate.py         process_vacancy + run_batch (called by apply.py)
  display.py             console formatting helpers
  ats_patterns.json      ATS regex list (edit here, not in batch.py)
prompts/                 prompt templates with $vars and ===CACHE_BREAKPOINT===
tests/                   unittest, mocked Anthropic client
output/<slug>/           per-vacancy artefacts (gitignored)
CV/, CL/                 user's source LaTeX (gitignored)
preferences.md           user's career preferences (gitignored)
notices/                 new vacancy notices land here (PDFs, gitignored)
.claude/skills/          Claude Code skill for vacancy pipeline triggering
```

## Commands

```bash
source .venv/bin/activate                              # required first
python -m unittest discover -s tests                   # run tests
ruff check .                                           # lint
ruff check --fix .                                     # auto-fix
python apply.py --vacancy <path|url> --slug <slug>     # full pipeline
python apply.py --mode batch --vacancies <…>           # batch
python apply.py --slug <slug> --mode adapt             # adapt only (reuses saved data)
python apply.py … --dry-run                            # estimate tokens, no API call
python apply.py … --backend api                        # use the Anthropic API instead of `claude -p`
```

Always activate `.venv` before running anything. Never `pip install` globally.

## Conventions

- **Prompts**: edit files in `prompts/`. Vars use `$name` (string.Template).
  Static prefix and variable suffix separated by `===CACHE_BREAKPOINT===` —
  static side is prompt-cached.
- **Models**: Sonnet for classification (analyse, batch_scan, verify,
  url-classifier). Opus for generation (report, adapt). Model IDs:
  `claude-sonnet-5-5`, `claude-opus-5-5`. Update all sites if you bump models.
- **Effort**: required `effort=` on every call (API: `output_config.effort`;
  CLI: `--effort`). Opus `high`; Sonnet `high` for analyse/verify, `medium`
  for batch scan + URL classifier.
- **Tool-use over JSON parsing** when the output is structured (see
  `analyse.ANALYSIS_TOOL`, `batch.SCAN_TOOL`). Sonnet/Opus 5.5 reject forced
  `tool_choice` (`"tool"`/`"any"`): use `{"type": "auto"}` and have the prompt
  tell the model to call the tool exactly once. Tools set `"strict": True`
  (needs `additionalProperties: False` on every object; no numeric/string
  constraints, no recursion).
- **Backends**: `--backend {api,cli}` (default `cli`), switched in
  `stages/_client.py` via `set_backend` (library default is `api`). `cli` runs
  each call as `claude -p` on the Claude Code subscription, returning
  Message-shaped namespaces so stages are unchanged. The child env drops
  `ANTHROPIC_API_KEY` (else billing moves to the API) and sets
  `CLAUDE_CODE_MAX_OUTPUT_TOKENS` from `max_tokens`. Argv isolates the call
  (`--system-prompt`, `--tools ""`, `--safe-mode --strict-mcp-config`) so no
  CLAUDE.md, memory or MCP context leaks in. Hitting the cap is a hard
  `RuntimeError` (no partial text, no `stop_reason == "max_tokens"` warning:
  that path is API-only). Batch scans use `CLI_MAX_SCAN_WORKERS = 1`. Risk: the
  Claude Code docs say `--bare` will become the default for `-p`; bare mode
  ignores OAuth, so `cli` would then fail with an auth error.
- **Output filenames** derive from the source `.tex` stem + slug. Don't
  hard-code `CV-hugocruces-` etc.
- **ATS patterns**: add to `stages/ats_patterns.json`, never re-inline in code.
- **Stage numbering**: 1 ingest, 2 analyse, 3 report, 4 adapt CV, 5 adapt CL,
  6 verify. Keep docstrings consistent.

## Code rules

- Default to no comments. Only add a comment when the *why* is non-obvious.
- Don't add error handling for impossible cases. Trust the schema/SDK.
- No backwards-compat shims unless asked. Just change the code.
- Prefer `Edit` over `Write` for existing files.
- Don't create new top-level docs (ROADMAP, CHANGELOG, NOTES, …) unless asked.
- Touch only what the task needs. No drive-by refactors.

## Workflow rules

- Non-trivial task (3+ steps or architectural): write a short plan, confirm
  with the user before coding.
- Run `ruff check .` and `python -m unittest discover -s tests` before
  declaring a task done. Both must be clean.
- If a test fails, stop and re-plan. Don't loosen the test to pass.
- For exploratory questions, answer in 2-3 sentences with a recommendation
  + tradeoff. Don't implement until the user agrees.

## Security / care

- `.env` holds `ANTHROPIC_API_KEY`. Gitignored. Never echo, log, or commit it.
- Never `git push --force` or `git reset --hard` without explicit ask.
- `output/`, `CV/`, `CL/`, `preferences.md`, `notices/` are gitignored —
  contain personal data. Don't add their contents to commits.
- Don't install new packages without asking. If you do, pin in
  `requirements.txt` (==) and update `pyproject.toml` if it's a dev tool.

## Subagent / context tips

- For locating code in 1-2 files, just use `Grep` / `Read`. The repo is small
  (~700 LOC) — Explore subagent is overkill.
- Use a subagent only for genuinely cross-cutting investigations (3+ files,
  multiple search angles).

## Open items + history

No open PLAN.md — all planned work is complete. Check `git log` for history of completed features.
