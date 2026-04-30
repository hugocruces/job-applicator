"""Batch scanning: quick-scan multiple vacancies in parallel and extract job URLs."""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from string import Template

from stages._client import call_simple, call_with_cache, strip_code_fence

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

SCAN_TOOL = {
    "name": "submit_scan",
    "description": "Submit a quick fit assessment of the candidate against the vacancy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "position_title": {"type": "string"},
            "organisation": {"type": "string"},
            "fit_score": {"type": "string", "enum": ["Strong", "Moderate", "Weak"]},
            "reason": {"type": "string"},
        },
        "required": ["position_title", "organisation", "fit_score", "reason"],
    },
}


def quick_scan(vacancy_text: str, cv_text: str) -> dict:
    """Quick Haiku scan of a single vacancy. Returns title, org, fit_score, reason."""
    prompt = Template((PROMPTS_DIR / "batch_scan.txt").read_text()).substitute(
        vacancy_text=vacancy_text, cv_text=cv_text,
    )

    message = call_with_cache(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        prompt=prompt,
        tools=[SCAN_TOOL],
        tool_choice={"type": "tool", "name": "submit_scan"},
        stage_label="Quick Scan",
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "submit_scan":
            return block.input
    raise RuntimeError("Quick scan: model did not return a submit_scan tool call.")


# Known ATS URL patterns that unambiguously identify individual job listings
_ATS_PATTERNS = [
    r"greenhouse\.io/.+/jobs/\d+",
    r"lever\.co/.+/.{8}-.{4}-.{4}-.{4}-.{12}",  # lever UUIDs
    r"jobs\.lever\.co/.+/.{8}-.{4}",
    r"myworkdayjobs\.com/.+/job/",
    r"taleo\.net/.+/requisition/",
    r"smartrecruiters\.com/.+/job/",
    r"ashbyhq\.com/.+/",
    r"breezy\.hr/.+/position/",
    r"workable\.com/.+/j/",
]
_ATS_RE = re.compile("|".join(_ATS_PATTERNS))


def extract_job_urls(page_url: str) -> list[str]:
    """
    Extract individual job listing URLs from a careers page.
    Uses Playwright to render JS-heavy pages. Tries a fast heuristic for known
    ATS platforms (Greenhouse, Lever, Workday, …) first; falls back to Claude
    Haiku classification when no ATS links are detected.
    """
    all_links = _fetch_links_playwright(page_url)
    if not all_links:
        return []

    all_links = list(dict.fromkeys(all_links))  # deduplicate, preserve order

    ats_links = [u for u in all_links if _ATS_RE.search(u)]
    if ats_links:
        return ats_links

    prompt = (
        f"You are given a list of URLs extracted from a careers/jobs page at: {page_url}\n\n"
        "Identify which URLs are individual job listing pages "
        "(i.e. a link to a single specific open position).\n"
        "IMPORTANT: job listings are often hosted on third-party ATS platforms "
        "(such as greenhouse.io, lever.co, workday, taleo, smartrecruiters, ashbyhq) "
        "and will therefore have a different domain from the careers page — include those.\n"
        "Exclude: the listing page itself, top-level navigation, login/signup, "
        "social media, pagination, and category/filter pages.\n"
        "Return ONLY a JSON array of individual job listing URLs. "
        "If none qualify, return [].\n\n"
        "URLs:\n" + "\n".join(all_links[:300])
    )

    message = call_simple(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        prompt=prompt,
        stage_label="URL Classifier",
    )

    text = strip_code_fence(message.content[0].text)
    try:
        urls = json.loads(text)
        return [u for u in urls if isinstance(u, str) and u.startswith("http")]
    except json.JSONDecodeError:
        return []


def _fetch_links_playwright(page_url: str) -> list[str]:
    """Render a page with Playwright (handles JS) and return all href values."""
    from stages._browser import render_page
    return render_page(page_url, what="links")


def scan_all(vacancies: list[tuple[str, str]], cv_text: str, max_workers: int = 5) -> list[dict]:
    """
    Quick-scan multiple vacancies in parallel.
    vacancies: list of (source_label, vacancy_text)
    Returns list of result dicts (same order as input), each with added 'source' and 'vacancy_text'.
    Failed scans get fit_score='Error' and a reason describing the failure.
    """
    results = [None] * len(vacancies)

    def scan_one(index: int, source: str, text: str):
        try:
            result = quick_scan(text, cv_text)
        except Exception as e:
            result = {
                "position_title": source,
                "organisation": "",
                "fit_score": "Error",
                "reason": str(e),
            }
        result["source"] = source
        result["vacancy_text"] = text
        return index, result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scan_one, i, source, text): i
            for i, (source, text) in enumerate(vacancies)
        }
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    return results


def make_slug(title: str, org: str) -> str:
    """Generate a URL-safe slug from position title and organisation."""
    combined = f"{title}-{org}"
    slug = re.sub(r"[^a-z0-9]+", "-", combined.lower()).strip("-")
    return slug[:60]


def parse_selection(raw: str, max_n: int) -> list[int]:
    """Parse user input like '1,3', '2-4', 'all' into sorted 0-based indices."""
    raw = raw.strip().lower()
    if raw in ("all", "*"):
        return list(range(max_n))

    indices: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                for i in range(int(start), int(end) + 1):
                    if 1 <= i <= max_n:
                        indices.add(i - 1)
            except ValueError:
                pass
        else:
            try:
                i = int(part)
                if 1 <= i <= max_n:
                    indices.add(i - 1)
            except ValueError:
                pass

    return sorted(indices)
