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

### 8. Optional batch cost ceiling
Currently `run_batch` will gleefully run Sonnet adapt on every selection if user
types `all`. Add a soft warning when estimated batch input tokens exceed a
threshold (e.g. 500k), or a `--max-cost` arg that aborts before stage 3 if the
estimate is above it. Skip if you trust yourself with `Ctrl-C`.

## Completed (do NOT redo)

Reference commits: `git log --oneline` for the exact history.

- Test for `extract_job_urls` Haiku-classifier fallback: two new tests in
  `tests/test_stages.py::TestExtractJobUrls` mock `_fetch_links_playwright`
  with non-ATS URLs to force the `call_simple` path, then assert (a) JSON
  parsing + `startswith("http")` filter (drops `mailto:`), (b) invalid JSON
  returns `[]`. Test count 42 → 44.
- mypy wired into CI: `.github/workflows/ci.yml` runs `mypy stages apply.py`
  after ruff. Three small annotation fixes to pass clean:
  `_browser.BrowserSession._pw/_browser` typed `Any`,
  `batch._fetch_links_playwright` casts `render` result to `list[str]`,
  `batch.scan_all` annotates `results: list[dict | None]` + `cast(list[dict], …)`
  on return.
- Playwright wait condition switched to `domcontentloaded`: `_browser.render`
  now uses `wait_until="domcontentloaded"` + `wait_for_timeout(1500)` for text
  (lets JS-rendered content paint without burning the 30s `networkidle`
  fallback). The `what="links"` path additionally awaits `wait_for_selector
  ("a[href]", timeout=5000)` so JS-injected links are caught.
- Centralised `preferences.md` read: read once in `apply.main`, passed as
  `preferences_text` into `analyse()`, `_dry_run_report()`, and
  `orchestrate.run_batch()`. `PREFERENCES_PATH` constant dropped from
  `stages/analyse.py`. `analyse()` keeps a default `preferences_text=""` so
  the existing test signatures still work.
- `parse_selection` warns on unparseable tokens: collects skipped tokens and
  emits one `WARNING` (`apply.batch` logger) listing them all. Empty parts
  skipped silently. Tests in `test_helpers.py` assert the warning fires
  once for garbage and not at all for clean input. Test count 40 → 42.
- Reuse one Chromium for batch rendering: `stages/_browser.py` now exposes a
  `BrowserSession` context manager (sync Playwright, lazy launch on first
  `render()`, closes on exit). `render_page` kept as a thin one-shot wrapper.
  `ingest()`/`_fetch_url`, `batch.extract_job_urls`/`_fetch_links_playwright`
  take an optional `browser=` arg; `orchestrate.collect_batch_sources` opens
  one session and threads it through all URL fetches. PDF-only batches never
  launch a browser.
- Concatenate all text blocks in adapt/report: `adapt._call_and_extract` and
  `report.generate_report` now `"".join` all `type == "text"` blocks before
  `strip_code_fence` (was `[0]` only — silently dropped tail content). Both
  raise `RuntimeError` if no text block present.
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
