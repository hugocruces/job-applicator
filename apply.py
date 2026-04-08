#!/usr/bin/env python3
"""Job Application Tool — adapt CV, cover letter, and generate interview prep report."""

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from stages.ingest import ingest
from stages.analyse import analyse
from stages.adapt import adapt_cv, adapt_cl
from stages.report import generate_report

ROOT = Path(__file__).resolve().parent


def find_tex(directory: Path, label: str) -> Path:
    """Return the single .tex file in directory, or raise a clear error."""
    files = list(directory.glob("*.tex"))
    if not files:
        raise FileNotFoundError(
            f"No .tex file found in {directory}/. Add your {label} as a .tex file there."
        )
    if len(files) > 1:
        names = ", ".join(f.name for f in files)
        raise ValueError(
            f"Multiple .tex files found in {directory}/: {names}. Keep only one."
        )
    return files[0]


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
    parser.add_argument(
        "--vacancy",
        help="Path to vacancy PDF or URL (required for 'all' and 'report' modes)",
    )
    parser.add_argument(
        "--vacancies",
        nargs="+",
        metavar="SOURCE",
        help="One or more PDF paths or URLs for batch mode",
    )
    parser.add_argument(
        "--slug",
        help="Short label for output filenames, e.g. efb-analyst (required for all/report/adapt)",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "report", "adapt", "batch"],
        default="all",
        help="Which stages to run (default: all)",
    )
    return parser


def run_single(
    slug: str,
    vacancy_text: str,
    analysis: dict,
    mode: str,
    cv_path: Path,
    cl_path: Path,
):
    """Run stages 3–5 for a single vacancy given pre-computed text and analysis."""
    cv_tex = cv_path.read_text()
    cl_tex = cl_path.read_text()

    output_dir = ROOT / "output" / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    if mode in ("all", "report"):
        print("Stage 3: Generating interview preparation report...")
        report = generate_report(vacancy_text, analysis, cv_tex)
        report_path = output_dir / f"report-{slug}.md"
        report_path.write_text(report)
        print(f"  Saved to {report_path}")

    if mode == "all":
        print("Stage 4: Adapting CV...")
        adapted_cv = adapt_cv(vacancy_text, analysis, cv_tex)
        cv_out = output_dir / f"{cv_path.stem}-{slug}.tex"
        cv_out.write_text(adapted_cv)
        print(f"  Saved to {cv_out}")

        print("Stage 5: Adapting cover letter...")
        adapted_cl = adapt_cl(vacancy_text, analysis, cl_tex)
        cl_out = output_dir / f"{cl_path.stem}-{slug}.tex"
        cl_out.write_text(adapted_cl)
        print(f"  Saved to {cl_out}")


def main():
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    cv_path = find_tex(ROOT / "CV", "CV")
    cl_path = find_tex(ROOT / "CL", "cover letter")
    cv_tex = cv_path.read_text()
    cl_tex = cl_path.read_text()

    # ── Batch mode ──────────────────────────────────────────────────────────
    if args.mode == "batch":
        from stages.batch import extract_job_urls, scan_all, make_slug, parse_selection

        if not args.vacancies:
            parser.error("--vacancies is required for batch mode")

        # Collect (source_label, vacancy_text) pairs
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

        # Quick-scan all in parallel
        print(f"\nScanning {len(sources)} vacancies (in parallel)...")
        results = scan_all(sources, cv_tex)

        # Sort: Strong → Moderate → Weak → Error
        score_order = {"Strong": 0, "Moderate": 1, "Weak": 2, "Error": 3}
        results.sort(key=lambda r: score_order.get(r.get("fit_score", "Error"), 3))

        # Display results
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

        # Interactive selection
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

        # Process each selected vacancy
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

            run_single(slug, vacancy_text, analysis, run_mode, cv_path, cl_path)
            print(f"\n  Done → {output_dir}/")

        print("\nAll selected vacancies processed.")
        return

    # ── Single-vacancy modes ─────────────────────────────────────────────────
    if not args.slug:
        parser.error("--slug is required for all/report/adapt modes")

    output_dir = ROOT / "output" / args.slug
    output_dir.mkdir(parents=True, exist_ok=True)

    vacancy_path = output_dir / f"vacancy-{args.slug}.txt"
    analysis_path = output_dir / f"analysis-{args.slug}.json"

    # Stages 1 & 2: Ingest + Analyse
    if args.mode in ("all", "report"):
        if not args.vacancy:
            parser.error("--vacancy is required for 'all' and 'report' modes")

        print("Stage 1: Ingesting vacancy notice...")
        vacancy_text = ingest(args.vacancy)
        vacancy_path.write_text(vacancy_text)
        print(f"  Extracted {len(vacancy_text)} characters.")

        print("Stage 2: Running gap analysis...")
        analysis = analyse(vacancy_text, cv_tex, cl_tex)
        analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
        print(f"  Fit score: {analysis.get('fit_score', 'N/A')}")
        print(f"  Analysis saved to {analysis_path}")

    # Stage 3: Report
    if args.mode in ("all", "report"):
        print("Stage 3: Generating interview preparation report...")
        report = generate_report(vacancy_text, analysis, cv_tex)
        report_path = output_dir / f"report-{args.slug}.md"
        report_path.write_text(report)
        print(f"  Saved to {report_path}")

    # Stages 4 & 5: Adapt
    if args.mode in ("all", "adapt"):
        if not vacancy_path.exists() or not analysis_path.exists():
            parser.error(
                f"No saved data found for slug '{args.slug}'. "
                "Run with --mode all or --mode report first."
            )
        if args.mode == "adapt":
            vacancy_text = vacancy_path.read_text()
            analysis = json.loads(analysis_path.read_text())

        print("Stage 4: Adapting CV...")
        adapted_cv = adapt_cv(vacancy_text, analysis, cv_tex)
        cv_out = output_dir / f"{cv_path.stem}-{args.slug}.tex"
        cv_out.write_text(adapted_cv)
        print(f"  Saved to {cv_out}")

        print("Stage 5: Adapting cover letter...")
        adapted_cl = adapt_cl(vacancy_text, analysis, cl_tex)
        cl_out = output_dir / f"{cl_path.stem}-{args.slug}.tex"
        cl_out.write_text(adapted_cl)
        print(f"  Saved to {cl_out}")

    print(f"\nDone! Outputs in {output_dir}/")


if __name__ == "__main__":
    main()
