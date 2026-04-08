"""Stage 1 — Vacancy Ingestion: parse vacancy notice into plain text."""

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import os

import pdfplumber
import requests
from bs4 import BeautifulSoup


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


def _fetch_url(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove script and style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    if not text.strip():
        raise ValueError(f"No text could be extracted from URL: {url}")
    return text
