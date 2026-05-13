# Improvement Plan — job-applicator

Continuation plan for future agent sessions. Tasks already shipped are listed in
"Completed" so you don't redo them. Open items below are ordered by impact.

## Context for the next agent

- Project: small Python CLI (`apply.py`) that ingests a vacancy (PDF or URL),
  runs gap analysis with Anthropic Claude, generates an interview-prep report,
  and adapts CV/cover letter LaTeX files. Stage modules in `stages/`.
- Tests: `python -m unittest discover -s tests` (40 tests, all green).
- Lint: `ruff check .` (clean). Config in `pyproject.toml`.
- Deps pinned in `requirements.txt`. Bootstrap via `bash setup.sh`.
- Run `source .venv/bin/activate` before any python/ruff commands.
- Anthropic API key in `.env` (gitignored). Don't commit it.
- All non-trivial work: write a short plan, confirm with the user before coding.

## Open items (ordered by impact)

### 3. Stage dataclass collapse  *(architectural — only if more stages coming)*
`analyse.py`, `report.py`, `adapt.py`, `batch.py` all do the same dance:
render template → call Claude → parse → write file.
- Define `@dataclass class Stage` with `name`, `prompt_template`, `model`,
  `max_tokens`, `tools`, `parser`, `output_filename` fields.
- Pipeline becomes a `list[Stage]` driven by one `run_stage()` function.
- Skip if no new stages are planned. Refactor for refactor's sake = bad.

## Completed (do NOT redo)

Reference commits: `git log --oneline` for the exact history.

- Structured logging: `stages/log.py` exposes `configure(quiet, verbose)` +
  `get_logger(name)`. Root logger `apply` writes to stderr with bare
  `%(message)s`. `apply.py` calls `configure_logging` after parsing args.
  CLI flags `--quiet` (WARNING) and `--verbose` (DEBUG); default INFO.
  Converted: `_client._log_usage` (DEBUG), `_client.call_with_cache`
  max_tokens warning (WARNING), `ingest._fetch_url` fallback (INFO),
  `orchestrate.*` prints (INFO/WARNING), `display.py` banners (INFO),
  `apply.py` prints (INFO), Playwright availability notes (WARNING).
- Infra:
  - `pyproject.toml` adds `[tool.mypy]` block (py3.10, `ignore_missing_imports`,
    `check_untyped_defs`, `warn_unused_ignores`, `warn_redundant_casts`).
    `mypy>=1.10` lives in `[project.optional-dependencies].dev`.
  - `.github/workflows/ci.yml`: ruff + unittest on push to main and on PRs,
    matrix over Python 3.10/3.11/3.12.
  - `tests/test_orchestrate.py`: integration test for
    `orchestrate.process_vacancy` (mocked client, tmp ROOT, verifies report
    + adapted CV/CL artefacts written and verify stage runs).
- `apply.py:check_playwright_available` memoised via module-global cache
  (`_playwright_available_cache`) — skips ~1s sync_playwright probe on
  repeat calls within a process.
- Nits bundle:
  - `warnings.filterwarnings` scoped to `module="urllib3"`.
  - `_TEX_HELPER_TOKENS` matching uses word boundaries (`\b{tok}\b`) to
    avoid substring false positives like `"old"` ⊂ `"scaffold"`.
  - `stages/adapt.py:_call_and_extract` filters text blocks and raises if
    none present rather than indexing blindly.
  - `_dry_run_report` uses `_DRY_RUN_ANALYSIS_STUB` (realistic JSON) for
    token estimates instead of `"{...}"` placeholder.
  - `setup.sh --dev` installs `[dev]` extras (ruff). Dev deps live in
    `pyproject.toml::[project.optional-dependencies].dev`.

- Split `apply.py` (375 → ~200 LOC) into `stages/orchestrate.py` (`process_vacancy`,
  `run_batch`, `collect_batch_sources`) + `stages/display.py`
  (`print_scan_results`, `print_vacancy_header`).
- `stages/verify.py`: strips LaTeX commands before fact-check; raises
  `RuntimeError` on JSON parse failure (was silent `[]`).
- `stages/report.py`: applies `strip_code_fence` with `("markdown","md")`.
- `stages/ingest.py`: chains HTTP error into Playwright fallback exception;
  logs when fallback triggers.
- `stages/batch.py`:
  - `make_slug` truncates at last dash within `max_len`.
  - ATS regex patterns externalised to `stages/ats_patterns.json` via
    `_load_ats_patterns()`. Lever UUID pattern tightened to hex-only.
  - Concurrency: `MAX_SCAN_WORKERS=3`, `_throttle()` enforces 250ms minimum
    interval between scan submissions.
- `stages/_client.py`:
  - `render_prompt(name, **vars)` hoisted; replaced 5 inline `Template` sites.
  - `estimate_tokens` uses Anthropic's `count_tokens` endpoint with
    `_heuristic_tokens` fallback (chars/4).
- Module docstrings: stage numbers corrected (`analyse=2`, `report=3`,
  `adapt=4-5`, `verify=6`).
- `README.md`: corrected CV/CL output filename description, added
  `playwright install chromium` step, added Stage 6 (verify) section.
- `pyproject.toml` (new): project metadata + ruff config (line-length 110,
  target py310, rules E/F/W/I/B/UP). Per-file ignore: `apply.py = ["E402"]`
  (warnings filter must precede urllib3 import).
- `requirements.txt`: pinned to `==` for reproducibility.
- Tests: 27 → 38. Added `_strip_latex` test, ATS match/non-match matrix (12),
  `find_tex` (5), `parse_selection` edge cases (4 more).

## House rules

- Always run `ruff check .` and `python -m unittest discover -s tests` before
  declaring a task done.
- Keep `print()` vs `logger` discipline if logging is added in #1.
- Don't introduce new top-level files (CLAUDE.md, ROADMAP.md, CHANGELOG.md,
  etc.) without asking the user.
- If you touch ATS patterns, update `stages/ats_patterns.json` — never
  re-inline them in `batch.py`.
- `.env` is gitignored. Do not commit it. Do not echo `ANTHROPIC_API_KEY`.
