"""Playwright-based page rendering helpers (shared across ingest and batch)."""

import asyncio


def render_page(page_url: str, what: str = "text") -> str | list[str]:
    """
    Render a page with Playwright (handles JS) and return either visible text
    (what='text') or all <a href> values (what='links').
    """

    async def _run():
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(page_url, wait_until="networkidle", timeout=30_000)
            if what == "links":
                result = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(el => el.href)"
                )
            else:
                result = await page.evaluate("() => document.body.innerText")
            await browser.close()
        return result

    return asyncio.run(_run())
