"""Pipeline orchestration: process a single vacancy through stages 3-6, and run batch mode."""

import json
import sys
from pathlib import Path

from stages.adapt import adapt_cl, adapt_cv
from stages.analyse import analyse
from stages.batch import extract_job_urls, make_slug, parse_selection, scan_all
from stages.display import print_scan_results, print_vacancy_header
from stages.ingest import ingest
from stages.report import generate_report

ROOT = Path(__file__).resolve().parent.parent


def process_vacancy(
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
) -> None:
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


def collect_batch_sources(items: list[str]) -> list[tuple[str, str]]:
    """Resolve each input (URL or PDF path) into (source_label, vacancy_text) pairs."""
    sources: list[tuple[str, str]] = []
    for item in items:
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
                    sources.append((url, ingest(url)))
                except Exception as e:
                    print(f"  Skipping {url}: {e}")
        else:
            try:
                sources.append((item, ingest(item)))
            except Exception as e:
                print(f"  Skipping {item}: {e}")
    return sources


def run_batch(
    items: list[str],
    cv_tex: str,
    cl_tex: str,
    cv_stem: str,
    cl_stem: str,
    verify: bool,
    dry_run: bool,
) -> None:
    """Full batch flow: collect → scan → user-select → process."""
    from stages._client import estimate_tokens

    print("Collecting vacancies...")
    sources = collect_batch_sources(items)

    if not sources:
        print("No vacancies to scan. Exiting.")
        sys.exit(0)

    if dry_run:
        total = sum(estimate_tokens(t) for _, t in sources)
        print(f"\nDry run: would quick-scan {len(sources)} vacancies "
              f"(≈ {total} input tokens, plus CV/CV reuse cached).")
        return

    print(f"\nScanning {len(sources)} vacancies (in parallel)...")
    results = scan_all(sources, cv_tex)

    score_order = {"Strong": 0, "Moderate": 1, "Weak": 2, "Error": 3}
    results.sort(key=lambda r: score_order.get(r.get("fit_score", "Error"), 3))

    print_scan_results(results)

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

        print_vacancy_header(title, org, slug)

        output_dir = ROOT / "output" / slug
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"vacancy-{slug}.txt").write_text(vacancy_text)

        print("Stage 2: Running gap analysis...")
        analysis = analyse(vacancy_text, cv_tex, cl_tex)
        analysis_path = output_dir / f"analysis-{slug}.json"
        analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
        print(f"  Fit score: {analysis.get('fit_score', 'N/A')}")

        process_vacancy(
            slug, vacancy_text, analysis, cv_tex, cl_tex, cv_stem, cl_stem,
            do_report=True,
            do_adapt=(run_mode == "all"),
            verify=verify,
        )
        print(f"\n  Done → {output_dir}/")

    print("\nAll selected vacancies processed.")
