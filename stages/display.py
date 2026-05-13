"""Console formatting helpers for batch mode output."""

from stages.log import get_logger

log = get_logger(__name__)

_MARKERS = {"Strong": "●●●", "Moderate": "●●○", "Weak": "●○○", "Error": "✗✗✗"}
_DIVIDER = "─" * 62
_HEAVY_DIVIDER = "═" * 62


def print_scan_results(results: list[dict]) -> None:
    """Print a ranked, formatted list of quick-scan results."""
    lines = ["", _DIVIDER]
    for i, r in enumerate(results, 1):
        fit = r.get("fit_score", "Error")
        title = r.get("position_title", r["source"])
        org = r.get("organisation", "")
        reason = r.get("reason", "")
        label = f"{title} · {org}" if org else title
        lines.append(f"\n  {i:>2}  [{_MARKERS.get(fit, '○○○')} {fit:<8}]  {label}")
        lines.append(f'       "{reason}"')
    lines.append("")
    lines.append(_DIVIDER)
    log.info("\n".join(lines))


def print_vacancy_header(title: str, org: str, slug: str) -> None:
    log.info("\n%s\n  %s · %s\n  slug: %s  →  output/%s/\n%s",
             _HEAVY_DIVIDER, title, org, slug, slug, _HEAVY_DIVIDER)
