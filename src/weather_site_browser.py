"""
WeatherSiteBrowser - all direct browser interaction with weather2day.co.il.

This module owns Playwright, the selectors, the waits and the text cleaning.
It knows nothing about MCP, so it can also be used from a plain Python script:

    browser = WeatherSiteBrowser()
    await browser.open()
    await browser.type_city("חיפה")
    await browser.pick_first_suggestion()
    print(await browser.read_forecast_text())
    await browser.close()

Configuration (environment variables, all optional):
    WEATHER_HEADLESS=1        run the browser without a window (default: visible)
    WEATHER_MAX_CHARS=6000    max characters returned by read_forecast_text

If a selector stops matching (sites change), record fresh ones with:
    uv run playwright codegen https://www.weather2day.co.il/forecast
"""

import os

from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright, Browser, Page, Playwright

# The MCP server runs as a subprocess that does not inherit the host's
# environment, so read .env here directly.
load_dotenv()

DEFAULT_TIMEOUT_MS = 15_000
HEADLESS = os.getenv("WEATHER_HEADLESS", "0") == "1"
MAX_CHARS = int(os.getenv("WEATHER_MAX_CHARS", "6000"))


class WeatherSiteError(Exception):
    """A browser step failed; the message is safe to show to the LLM."""


class WeatherSiteBrowser:
    """Owns the single browser tab and every interaction with weather2day.

    The flow open -> type_city -> pick_first_suggestion -> read_forecast_text
    happens in the SAME tab, just like a real user would do it.
    """

    URL = "https://www.weather2day.co.il/forecast"

    # --- Selectors (recorded with playwright codegen) ----------------------------
    SEARCH_INPUT = "#city_search_forecast"
    SUGGESTION_ITEM = "#city_search_forecastautocomplete-list div"
    CONTENT = "main, #forecast, .forecast-content, article, body"
    # Elements that never contain forecast data - removed before extracting text.
    NOISE = "script, style, noscript, iframe, nav, header, footer, aside, form, .ad, [class*='banner']"
    # ------------------------------------------------------------------------------

    def __init__(self, headless: bool = HEADLESS, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self.city: str | None = None

    @property
    def is_open(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    @property
    def current_url(self) -> str:
        return self._page.url if self.is_open else ""  # type: ignore[union-attr]

    async def open(self) -> str:
        """Start a fresh browser and load the forecast page. Returns the URL."""
        await self.close()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page(locale="he-IL")
        self._page.set_default_timeout(self.timeout_ms)
        try:
            await self._page.goto(self.URL, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            await self.close()
            raise WeatherSiteError(f"Timed out loading {self.URL}. Try again in a moment.")
        return self.URL

    async def type_city(self, city: str) -> list[str]:
        """Type the city into the search box. Returns the dropdown suggestions."""
        city = city.strip()
        if not city:
            raise WeatherSiteError("City name is empty - please provide a city.")

        page = await self._get_page()
        try:
            search_box = page.locator(self.SEARCH_INPUT).first
            await search_box.wait_for(state="visible")
            await search_box.fill("")
            # Typing key by key (not fill) fires the site's autocomplete JS.
            await search_box.press_sequentially(city, delay=60)
            await page.locator(self.SUGGESTION_ITEM).first.wait_for(state="visible")
        except PlaywrightTimeout:
            raise WeatherSiteError(
                f"Typed '{city}' but no suggestions appeared. The city may not exist "
                f"on the site - try the Hebrew spelling or a nearby larger city."
            )

        self.city = city
        suggestions = await page.locator(self.SUGGESTION_ITEM).all_inner_texts()
        return [s.strip() for s in suggestions if s.strip()]

    async def pick_first_suggestion(self) -> tuple[str, str]:
        """Click the first dropdown item. Returns (chosen city, forecast URL)."""
        page = await self._get_page()
        item = page.locator(self.SUGGESTION_ITEM).first
        if await item.count() == 0:
            raise WeatherSiteError(
                "No suggestion list is open. Call enter_weather_forecast_city_israel first."
            )

        try:
            chosen = (await item.inner_text()).strip()
            url_before = page.url
            await item.click()
            # Wait until the browser actually leaves the search page.
            await page.wait_for_url(lambda url: url != url_before)
            await page.wait_for_load_state("domcontentloaded")
        except PlaywrightTimeout:
            raise WeatherSiteError("Clicked the first suggestion but the forecast page did not load.")

        self.city = chosen or self.city
        return chosen, page.url

    async def read_forecast_text(self, max_chars: int = MAX_CHARS) -> str:
        """Return the cleaned visible text of the current forecast page."""
        if not self.is_open:
            raise WeatherSiteError(
                "No forecast page is open. Run the open -> enter -> select tools first."
            )
        page = self._page
        assert page is not None

        # Strip menus, ads, scripts etc. from the DOM so only real content is left.
        await page.evaluate(
            "(sel) => document.querySelectorAll(sel).forEach(el => el.remove())",
            self.NOISE,
        )
        try:
            raw_text = await page.locator(self.CONTENT).first.inner_text()
        except PlaywrightTimeout:
            raw_text = await page.locator("body").inner_text()

        text = self._clean_text(raw_text)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...[truncated]"
        return text

    async def close(self) -> None:
        """Close the browser and Playwright; safe to call more than once."""
        for close in (
            self._browser.close if self._browser else None,
            self._playwright.stop if self._playwright else None,
        ):
            if close is None:
                continue
            try:
                await close()
            except Exception:
                pass
        self._playwright = self._browser = self._page = None

    async def _get_page(self) -> Page:
        """Return the open page; if the LLM skipped the 'open' step (or the
        user closed the window), recover by opening it instead of failing."""
        if not self.is_open:
            await self.open()
        return self._page  # type: ignore[return-value]

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalize raw innerText: collapse whitespace, drop empty lines and
        back-to-back duplicates. Non-adjacent repeats are kept on purpose - the
        same temperature can legitimately appear on different days."""
        result: list[str] = []
        for line in text.splitlines():
            line = " ".join(line.split())
            if not line or (result and result[-1] == line):
                continue
            result.append(line)
        return "\n".join(result)
