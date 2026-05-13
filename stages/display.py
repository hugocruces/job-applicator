"""Console formatting helpers for batch mode output."""

_MARKERS = {"Strong": "●●●", "Moderate": "●●○", "Weak": "●○○", "Error": "✗✗✗"}
_DIVIDER = "─" * 62
_HEAVY_DIVIDER = "═" * 62


def print_scan_results(results: list[dict]) -> None:
    """Print a ranked, formatted list of quick-scan results."""
    print(f"\n{_DIVIDER}")
    for i, r in enumerate(results, 1):
        fit = r.get("fit_score", "Error")
        title = r.get("position_title", r["source"])
        org = r.get("organisation", "")
        reason = r.get("reason", "")
        label = f"{title} · {org}" if org else title
        print(f"\n  {i:>2}  [{_MARKERS.get(fit, '○○○')} {fit:<8}]  {label}")
        print(f"       \"{reason}\"")
    print(f"\n{_DIVIDER}")


def print_vacancy_header(title: str, org: str, slug: str) -> None:
    print(f"\n{_HEAVY_DIVIDER}")
    print(f"  {title} · {org}")
    print(f"  slug: {slug}  →  output/{slug}/")
    print(f"{_HEAVY_DIVIDER}")
