"""Playwright-based page rendering helpers (shared across ingest and batch)."""


class BrowserSession:
    """
    Reusable headless Chromium. Launches lazily on the first render() call and
    closes on context exit, so a batch run pays one cold launch instead of N+1.
    PDF-only batches never launch a browser at all.
    """

    def __init__(self) -> None:
        self._pw = None
        self._browser = None

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
            page.goto(page_url, wait_until="networkidle", timeout=30_000)
            if what == "links":
                return page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
            return page.evaluate("() => document.body.innerText")
        finally:
            page.close()


def render_page(page_url: str, what: str = "text") -> str | list[str]:
    """One-shot render: launch a browser, render a single page, close. Thin
    wrapper over BrowserSession for the single-vacancy flow."""
    with BrowserSession() as session:
        return session.render(page_url, what=what)
