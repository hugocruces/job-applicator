"""Stage 1 — Vacancy Ingestion: parse vacancy notice into plain text."""

import os

import pdfplumber
import requests
from bs4 import BeautifulSoup

from stages.log import get_logger

log = get_logger(__name__)


def ingest(source: str) -> str:
    """Return plain text from a PDF path or URL."""
    if os.path.isfile(source):
        return _extract_pdf(source)
    if source.startswith(("http://", "https://")):
        return _fetch_url(source)
    raise ValueError(f"Source is neither a valid file path nor a URL: {source}")


def _extract_pdf(path: str) -> str:
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    if not pages:
        raise ValueError(f"No text could be extracted from PDF: {path}")
    return "\n\n".join(pages)


# If a requests-based fetch returns less than this much text, the page is
# probably JS-rendered and we should re-fetch with a headless browser.
_THIN_TEXT_THRESHOLD = 500


def _fetch_url(url: str) -> str:
    text = ""
    http_error: Exception | None = None
    try:
        resp = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; job-applicator/1.0)"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except requests.RequestException as e:
        http_error = e

    if len(text) < _THIN_TEXT_THRESHOLD:
        if http_error is None:
            log.info("  Page returned only %d chars; retrying with Playwright...", len(text))
        try:
            from stages._browser import render_page
            rendered = render_page(url, what="text")
            if isinstance(rendered, str) and rendered.strip():
                text = rendered
        except Exception as e:
            if not text:
                raise ValueError(
                    f"Failed to fetch {url}. HTTP error: {http_error}. Playwright error: {e}"
                ) from e

    if not text.strip():
        raise ValueError(f"No text could be extracted from URL: {url}")
    return text
