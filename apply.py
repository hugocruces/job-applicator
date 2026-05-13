#!/usr/bin/env python3
"""Job Application Tool — adapt CV, cover letter, and generate interview prep report."""

import warnings

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL", module="urllib3")

import json
import re
from pathlib import Path

from dotenv import load_dotenv

from stages._client import estimate_tokens, render_prompt
from stages.analyse import analyse
from stages.ingest import ingest
from stages.orchestrate import process_vacancy, run_batch

ROOT = Path(__file__).resolve().parent

# Files matching any of these patterns are skipped by find_tex (treated as helpers).
_TEX_HELPER_TOKENS = ("old", "bak", "backup", "draft", "tmp", "scratch", "wip")


def find_tex(directory: Path, label: str, override: str | None = None) -> Path:
    """Return the canonical .tex file in directory, or raise a clear error."""
    if override:
        path = Path(override)
        if not path.is_absolute():
            path = directory / override
        if not path.exists():
            raise FileNotFoundError(f"--{label.replace(' ', '-')}-file: {path} does not exist.")
        return path

    files = [
        f for f in directory.glob("*.tex")
        if not any(re.search(rf"\b{tok}\b", f.stem.lower()) for tok in _TEX_HELPER_TOKENS)
    ]
    if not files:
        raise FileNotFoundError(
            f"No .tex file found in {directory}/. Add your {label} as a .tex file there."
        )
    if len(files) > 1:
        names = ", ".join(f.name for f in files)
        raise ValueError(
            f"Multiple .tex files found in {directory}/: {names}. "
            f"Keep only one, rename helpers (with 'old'/'draft'/'tmp' etc.), "
            f"or pass --{label.replace(' ', '-')}-file."
        )
    return files[0]


_playwright_available_cache: bool | None = None


def check_playwright_available() -> bool:
    """Return True if Playwright + Chromium look usable. Print a friendly note otherwise.

    Memoised: spawning sync_playwright costs ~1s, so we only probe once per process.
    """
    global _playwright_available_cache
    if _playwright_available_cache is not None:
        return _playwright_available_cache
    try:
        import playwright  # noqa: F401
    except ImportError:
        print(
            "NOTE: Playwright not installed. URL ingestion will fall back to plain HTTP only,\n"
            "      and batch mode --vacancies <url> will not work. Run: pip install playwright && playwright install chromium"
        )
        _playwright_available_cache = False
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _ = p.chromium.executable_path
    except Exception as e:
        print(f"NOTE: Playwright is installed but Chromium is not ready ({e}). Run: playwright install chromium")
        _playwright_available_cache = False
        return False
    _playwright_available_cache = True
    return True


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Adapt CV and cover letter for a specific vacancy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
modes:
  all     (default) Ingest → Gap analysis → Report → Adapt CV → Adapt CL
  report  Ingest → Gap analysis → Report only (no document adaptation)
  adapt   Adapt CV → Adapt CL only (reuses saved vacancy text and analysis)
  batch   Quick-scan multiple vacancies, then run full pipeline on selected ones
        """,
    )
    parser.add_argument("--vacancy", help="Path to vacancy PDF or URL")
    parser.add_argument("--vacancies", nargs="+", metavar="SOURCE",
                        help="One or more PDF paths or URLs for batch mode")
    parser.add_argument("--slug", help="Short label for output filenames, e.g. efb-analyst")
    parser.add_argument("--mode", choices=["all", "report", "adapt", "batch"], default="all",
                        help="Which stages to run (default: all)")
    parser.add_argument("--cv-file", help="Override the auto-detected CV .tex file")
    parser.add_argument("--cl-file", help="Override the auto-detected cover letter .tex file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Estimate prompt sizes and exit without calling the API")
    parser.add_argument("--verify", action="store_true",
                        help="Run a post-adaptation sanity check (Haiku) to flag fabricated phrases")
    return parser


_DRY_RUN_ANALYSIS_STUB = json.dumps({
    "position_title": "Senior Research Analyst",
    "organisation": "Example Foundation",
    "key_requirements": {
        "must_haves": [
            "PhD in economics or related field",
            "Experience with causal inference methods",
            "Strong Python and Stata skills",
            "Publication record in peer-reviewed journals",
        ],
        "nice_to_haves": [
            "Experience with machine learning",
            "Policy engagement background",
        ],
    },
    "strengths": [
        "Strong quantitative background with causal inference experience",
        "Demonstrated publication record",
        "Proficiency in required tools",
    ],
    "gaps": [
        "Limited direct policy engagement experience",
        "No prior work in the organisation's specific subfield",
    ],
    "fit_score": "Strong",
    "fit_summary": "Candidate's methodological skills align closely with role requirements.",
    "personal_objectives_fit": {
        "aligned": ["Research autonomy", "Distributional issues focus"],
        "misaligned": [],
        "unknown": ["Remote work policy"],
        "summary": "Role aligns well with stated career objectives.",
    },
}, indent=2)


def _dry_run_report(slug: str, vacancy_text: str, cv_tex: str, cl_tex: str, mode: str) -> None:
    """Estimate prompt sizes for each stage that would run; no API calls."""
    preferences_path = ROOT / "preferences.md"
    preferences_text = preferences_path.read_text() if preferences_path.exists() else ""

    estimates: list[tuple[str, int]] = []
    if mode in ("all", "report"):
        p = render_prompt("analyse.txt",
                          vacancy_text=vacancy_text, cv_text=cv_tex,
                          cl_text=cl_tex, preferences_text=preferences_text)
        estimates.append(("Gap Analysis (Haiku)", estimate_tokens(p)))
        p = render_prompt("report.txt",
                          vacancy_text=vacancy_text, cv_text=cv_tex,
                          analysis_json=_DRY_RUN_ANALYSIS_STUB)
        estimates.append(("Report (Sonnet)", estimate_tokens(p)))
    if mode == "all":
        p = render_prompt("adapt_cv.txt",
                          vacancy_text=vacancy_text, cv_tex=cv_tex,
                          analysis_json=_DRY_RUN_ANALYSIS_STUB)
        estimates.append(("Adapt CV (Sonnet)", estimate_tokens(p)))
        p = render_prompt("adapt_cl.txt",
                          vacancy_text=vacancy_text, cl_tex=cl_tex,
                          analysis_json=_DRY_RUN_ANALYSIS_STUB)
        estimates.append(("Adapt CL (Sonnet)", estimate_tokens(p)))

    print(f"\nDry run for slug={slug!r} mode={mode!r}:")
    for label, n in estimates:
        print(f"  {label:30s} ≈ {n:>6} input tokens")
    print(f"  {'TOTAL input (no caching)':30s} ≈ {sum(n for _, n in estimates):>6} tokens")
    print("  (note: with prompt caching, repeated CV/CL/preferences are billed at ~10%)")


def main():
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    cv_path = find_tex(ROOT / "CV", "CV", override=args.cv_file)
    cl_path = find_tex(ROOT / "CL", "cover letter", override=args.cl_file)
    cv_tex = cv_path.read_text()
    cl_tex = cl_path.read_text()

    needs_browser = args.mode == "batch" or (args.vacancy and args.vacancy.startswith(("http://", "https://")))
    if needs_browser and not args.dry_run:
        check_playwright_available()

    if args.mode == "batch":
        if not args.vacancies:
            parser.error("--vacancies is required for batch mode")
        run_batch(
            args.vacancies, cv_tex, cl_tex, cv_path.stem, cl_path.stem,
            verify=args.verify, dry_run=args.dry_run,
        )
        return

    if not args.slug:
        parser.error("--slug is required for all/report/adapt modes")

    output_dir = ROOT / "output" / args.slug
    vacancy_path = output_dir / f"vacancy-{args.slug}.txt"
    analysis_path = output_dir / f"analysis-{args.slug}.json"
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    vacancy_text: str = ""
    analysis: dict = {}

    if args.mode in ("all", "report"):
        if not args.vacancy:
            parser.error("--vacancy is required for 'all' and 'report' modes")

        print("Stage 1: Ingesting vacancy notice...")
        vacancy_text = ingest(args.vacancy)
        print(f"  Extracted {len(vacancy_text)} characters.")

        if args.dry_run:
            _dry_run_report(args.slug, vacancy_text, cv_tex, cl_tex, args.mode)
            return

        vacancy_path.write_text(vacancy_text)

        print("Stage 2: Running gap analysis...")
        analysis = analyse(vacancy_text, cv_tex, cl_tex)
        analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
        print(f"  Fit score: {analysis.get('fit_score', 'N/A')}")
        print(f"  Analysis saved to {analysis_path}")

    elif args.mode == "adapt":
        if not vacancy_path.exists() or not analysis_path.exists():
            parser.error(
                f"No saved data found for slug '{args.slug}'. "
                "Run with --mode all or --mode report first."
            )
        vacancy_text = vacancy_path.read_text()
        analysis = json.loads(analysis_path.read_text())

        if args.dry_run:
            _dry_run_report(args.slug, vacancy_text, cv_tex, cl_tex, args.mode)
            return

    process_vacancy(
        args.slug, vacancy_text, analysis, cv_tex, cl_tex,
        cv_path.stem, cl_path.stem,
        do_report=args.mode in ("all", "report"),
        do_adapt=args.mode in ("all", "adapt"),
        verify=args.verify,
    )

    print(f"\nDone! Outputs in {output_dir}/")


if __name__ == "__main__":
    main()
