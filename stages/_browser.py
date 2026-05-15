"""Playwright-based page rendering helpers (shared across ingest and batch)."""

from typing import Any


class BrowserSession:
    """
    Reusable headless Chromium. Launches lazily on the first render() call and
    closes on context exit, so a batch run pays one cold launch instead of N+1.
    PDF-only batches never launch a browser at all.
    """

    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Any = None

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *exc) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    def render(self, page_url: str, what: str = "text") -> str | list[str]:
        """
        Render a page (handles JS) and return either visible text (what='text')
        or all <a href> values (what='links').
        """
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)

        page = self._browser.new_page()
        try:
            # networkidle is unreliable on real careers pages (analytics
            # beacons, chat widgets often keep the network busy past the 30s
            # timeout). domcontentloaded + a short paint settle is enough.
            page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
            if what == "links":
                try:
                    page.wait_for_selector("a[href]", timeout=5_000)
                except Exception:
                    pass
                return page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
            page.wait_for_timeout(1_500)
            return page.evaluate("() => document.body.innerText")
        finally:
            page.close()


def render_page(page_url: str, what: str = "text") -> str | list[str]:
    """One-shot render: launch a browser, render a single page, close. Thin
    wrapper over BrowserSession for the single-vacancy flow."""
    with BrowserSession() as session:
        return session.render(page_url, what=what)
