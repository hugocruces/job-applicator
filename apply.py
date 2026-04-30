#!/usr/bin/env python3
"""Job Application Tool — adapt CV, cover letter, and generate interview prep report."""

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import json
import sys
from pathlib import Path
from string import Template

from dotenv import load_dotenv

from stages.adapt import adapt_cv, adapt_cl
from stages.analyse import analyse
from stages.ingest import ingest
from stages.report import generate_report
from stages._client import estimate_tokens

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
        if not any(tok in f.stem.lower() for tok in _TEX_HELPER_TOKENS)
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


def check_playwright_available() -> bool:
    """Return True if Playwright + Chromium look usable. Print a friendly note otherwise."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        print(
            "NOTE: Playwright not installed. URL ingestion will fall back to plain HTTP only,\n"
            "      and batch mode --vacancies <url> will not work. Run: pip install playwright && playwright install chromium"
        )
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Touching .executable_path raises if the browser isn't installed.
            _ = p.chromium.executable_path
    except Exception as e:
        print(f"NOTE: Playwright is installed but Chromium is not ready ({e}). Run: playwright install chromium")
        return False
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


def _dry_run_report(slug: str, vacancy_text: str, cv_tex: str, cl_tex: str, mode: str) -> None:
    """Estimate prompt sizes for each stage that would run; no API calls."""
    preferences_path = ROOT / "preferences.md"
    preferences_text = preferences_path.read_text() if preferences_path.exists() else ""

    def render(name: str, **vars) -> str:
        return Template((ROOT / "prompts" / name).read_text()).substitute(**vars)

    estimates: list[tuple[str, int]] = []
    if mode in ("all", "report"):
        p = render("analyse.txt",
                   vacancy_text=vacancy_text, cv_text=cv_tex,
                   cl_text=cl_tex, preferences_text=preferences_text)
        estimates.append(("Gap Analysis (Haiku)", estimate_tokens(p)))
        p = render("report.txt",
                   vacancy_text=vacancy_text, cv_text=cv_tex, analysis_json="{...}")
        estimates.append(("Report (Sonnet)", estimate_tokens(p)))
    if mode == "all":
        p = render("adapt_cv.txt",
                   vacancy_text=vacancy_text, cv_tex=cv_tex, analysis_json="{...}")
        estimates.append(("Adapt CV (Sonnet)", estimate_tokens(p)))
        p = render("adapt_cl.txt",
                   vacancy_text=vacancy_text, cl_tex=cl_tex, analysis_json="{...}")
        estimates.append(("Adapt CL (Sonnet)", estimate_tokens(p)))

    print(f"\nDry run for slug={slug!r} mode={mode!r}:")
    for label, n in estimates:
        print(f"  {label:30s} ≈ {n:>6} input tokens")
    print(f"  {'TOTAL input (no caching)':30s} ≈ {sum(n for _, n in estimates):>6} tokens")
    print("  (note: with prompt caching, repeated CV/CL/preferences are billed at ~10%)")


def run_stages_3_to_6(
    slug: str,
    vacancy_text: str,
    analysis: dict,
    cv_tex: str,
    cl_tex: str,
    cv_stem: str,
    cl_stem: str,
    do_report: bool,
    do_adapt: bool,
    verify: bool,
):
    """Run report and/or adapt for a single vacancy given pre-computed text and analysis."""
    output_dir = ROOT / "output" / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    if do_report:
        print("Stage 3: Generating interview preparation report...")
        report = generate_report(vacancy_text, analysis, cv_tex)
        report_path = output_dir / f"report-{slug}.md"
        report_path.write_text(report)
        print(f"  Saved to {report_path}")

    if do_adapt:
        print("Stage 4: Adapting CV...")
        adapted_cv = adapt_cv(vacancy_text, analysis, cv_tex)
        cv_out = output_dir / f"{cv_stem}-{slug}.tex"
        cv_out.write_text(adapted_cv)
        print(f"  Saved to {cv_out}")

        print("Stage 5: Adapting cover letter...")
        adapted_cl = adapt_cl(vacancy_text, analysis, cl_tex)
        cl_out = output_dir / f"{cl_stem}-{slug}.tex"
        cl_out.write_text(adapted_cl)
        print(f"  Saved to {cl_out}")

        if verify:
            from stages.verify import find_fabrications
            print("Stage 6: Verifying adapted documents for fabricated phrases...")
            for kind, original, adapted in [("CV", cv_tex, adapted_cv), ("CL", cl_tex, adapted_cl)]:
                bad = find_fabrications(original, adapted, label=f"Verify {kind}")
                if bad:
                    print(f"  ⚠ {kind}: {len(bad)} potentially fabricated phrase(s):")
                    for s in bad:
                        print(f"      - {s}")
                else:
                    print(f"  ✓ {kind}: no fabrications detected")


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

    # ── Batch mode ──────────────────────────────────────────────────────────
    if args.mode == "batch":
        from stages.batch import extract_job_urls, scan_all, make_slug, parse_selection

        if not args.vacancies:
            parser.error("--vacancies is required for batch mode")

        print("Collecting vacancies...")
        sources: list[tuple[str, str]] = []

        for item in args.vacancies:
            if item.startswith(("http://", "https://")):
                print(f"  Extracting job listings from {item}...")
                try:
                    job_urls = extract_job_urls(item)
                except Exception as e:
                    print(f"  Failed to fetch page: {e}")
                    continue

                if not job_urls:
                    print("  No individual job listings found on that page.")
                    continue

                print(f"  Found {len(job_urls)} listings. Fetching...")
                for url in job_urls:
                    try:
                        text = ingest(url)
                        sources.append((url, text))
                    except Exception as e:
                        print(f"  Skipping {url}: {e}")
            else:
                try:
                    text = ingest(item)
                    sources.append((item, text))
                except Exception as e:
                    print(f"  Skipping {item}: {e}")

        if not sources:
            print("No vacancies to scan. Exiting.")
            sys.exit(0)

        if args.dry_run:
            total = sum(estimate_tokens(t) for _, t in sources)
            print(f"\nDry run: would quick-scan {len(sources)} vacancies "
                  f"(≈ {total} input tokens, plus CV/CV reuse cached).")
            return

        print(f"\nScanning {len(sources)} vacancies (in parallel)...")
        results = scan_all(sources, cv_tex)

        score_order = {"Strong": 0, "Moderate": 1, "Weak": 2, "Error": 3}
        results.sort(key=lambda r: score_order.get(r.get("fit_score", "Error"), 3))

        divider = "─" * 62
        print(f"\n{divider}")
        markers = {"Strong": "●●●", "Moderate": "●●○", "Weak": "●○○", "Error": "✗✗✗"}
        for i, r in enumerate(results, 1):
            fit = r.get("fit_score", "Error")
            title = r.get("position_title", r["source"])
            org = r.get("organisation", "")
            reason = r.get("reason", "")
            label = f"{title} · {org}" if org else title
            print(f"\n  {i:>2}  [{markers.get(fit, '○○○')} {fit:<8}]  {label}")
            print(f"       \"{reason}\"")
        print(f"\n{divider}")

        selection_raw = input(
            "\nSelect vacancies to process (e.g. 1,3 or 2-4 or all), or Enter to exit: "
        ).strip()
        if not selection_raw:
            print("Nothing selected. Exiting.")
            sys.exit(0)

        selected = parse_selection(selection_raw, len(results))
        if not selected:
            print("No valid selection. Exiting.")
            sys.exit(0)

        mode_raw = input(
            "Run which mode for selected? [all/report] (default: report): "
        ).strip().lower()
        run_mode = "all" if mode_raw == "all" else "report"

        for idx in selected:
            r = results[idx]
            title = r.get("position_title", "position")
            org = r.get("organisation", "org")
            slug = make_slug(title, org)
            vacancy_text = r["vacancy_text"]

            print(f"\n{'═' * 62}")
            print(f"  {title} · {org}")
            print(f"  slug: {slug}  →  output/{slug}/")
            print(f"{'═' * 62}")

            output_dir = ROOT / "output" / slug
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"vacancy-{slug}.txt").write_text(vacancy_text)

            print("Stage 2: Running gap analysis...")
            analysis = analyse(vacancy_text, cv_tex, cl_tex)
            analysis_path = output_dir / f"analysis-{slug}.json"
            analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
            print(f"  Fit score: {analysis.get('fit_score', 'N/A')}")

            run_stages_3_to_6(
                slug, vacancy_text, analysis, cv_tex, cl_tex,
                cv_path.stem, cl_path.stem,
                do_report=True,
                do_adapt=(run_mode == "all"),
                verify=args.verify,
            )
            print(f"\n  Done → {output_dir}/")

        print("\nAll selected vacancies processed.")
        return

    # ── Single-vacancy modes ─────────────────────────────────────────────────
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

    run_stages_3_to_6(
        args.slug, vacancy_text, analysis, cv_tex, cl_tex,
        cv_path.stem, cl_path.stem,
        do_report=args.mode in ("all", "report"),
        do_adapt=args.mode in ("all", "adapt"),
        verify=args.verify,
    )

    print(f"\nDone! Outputs in {output_dir}/")


if __name__ == "__main__":
    main()
