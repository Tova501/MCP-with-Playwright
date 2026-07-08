"""
MCP Server: weather-Israel
Fetches Israeli weather forecasts by driving a real browser (Playwright)
against https://www.weather2day.co.il/forecast instead of calling an API.

Tools exposed:
    1. open_weather_forecast_israel        - opens the browser & navigates to the forecast page
    2. enter_weather_forecast_city_israel  - types a city name into the search box
    3. select_weather_forecast_city_israel - clicks the first item in the autocomplete dropdown
    4. get_weather_forecast_content_israel - extracts & cleans the resulting page's text (RAG)

IMPORTANT - SELECTORS:
The three CSS selectors below (SEARCH_INPUT_SELECTOR, DROPDOWN_ITEM_SELECTOR,
FORECAST_CONTENT_SELECTOR) were written from a best-effort guess at the site's
markup. Websites change / use dynamic classes, so if a tool call fails with a
PlaywrightTimeout, the fastest fix is:

    uv run playwright codegen https://www.weather2day.co.il/forecast

This opens a browser + inspector. Click into the city search box and pick a
city manually - the Inspector panel will show you the exact selector Playwright
recorded. Paste the corrected selector(s) into the constants below.
"""

from mcp.server.fastmcp import FastMCP
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright, Browser, Page, Playwright

mcp = FastMCP("weather-Israel")

FORECAST_URL = "https://www.weather2day.co.il/forecast"

# --- Tune these if the site's markup differs from the recorded selectors here ---------
# This uses the Playwright selector engines recorded by codegen.
SEARCH_INPUT_SELECTOR = "id=city_search_forecast"
DROPDOWN_ITEM_SELECTOR = "#city_search_forecastautocomplete-list div"
FORECAST_CONTENT_SELECTOR = "main, #forecast, .forecast-content, article, body"
# --------------------------------------------------------------------------------

DEFAULT_TIMEOUT_MS = 15_000

# Module-level browser state so consecutive tool calls (open -> enter -> select)
# reuse the SAME browser tab, since a real user would not re-open the browser
# for every step of the flow.
_state: dict[str, Playwright | Browser | Page | None] = {
    "playwright": None,
    "browser": None,
    "page": None,
}


async def _ensure_page() -> Page:
    """Raise a clear error if a tool is called out of order (e.g. entering a
    city before the browser was opened)."""
    page = _state.get("page")
    if page is None:
        raise RuntimeError(
            "No open browser page. Call open_weather_forecast_israel first."
        )
    return page  # type: ignore[return-value]


@mcp.tool()
async def open_weather_forecast_israel() -> str:
    """Open a browser and navigate to the Israeli weather forecast website
    (weather2day.co.il/forecast). Call this first, before searching for a city.
    """
    # Clean up any previous session so repeated calls don't leak browsers.
    await _close_browser()

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page(locale="he-IL")

    _state["playwright"] = playwright
    _state["browser"] = browser
    _state["page"] = page

    try:
        await page.goto(FORECAST_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightTimeout:
        await _close_browser()
        return f"Timed out loading {FORECAST_URL}."

    return f"Opened {FORECAST_URL} successfully. You can now search for a city."


@mcp.tool()
async def enter_weather_forecast_city_israel(city: str) -> str:
    """Type a city name into the forecast website's search field.

    Args:
        city: The Hebrew (or English) name of the Israeli city to search for,
              e.g. "תל אביב" or "חיפה".
    """
    page = await _ensure_page()

    try:
        locator = page.locator(SEARCH_INPUT_SELECTOR).first
        await locator.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
        await locator.click()
        await locator.fill("")
        await locator.type(city, delay=60)  # slow typing helps trigger autocomplete JS
        # Give the site's JS a moment to render the dropdown.
        await page.wait_for_timeout(800)
    except PlaywrightTimeout:
        return (
            f"Could not find the city search input using selector "
            f"'{SEARCH_INPUT_SELECTOR}'. The site's markup may differ - "
            f"see the SELECTORS note at the top of weather_Israel.py."
        )

    return f"Typed '{city}' into the search field."


@mcp.tool()
async def select_weather_forecast_city_israel() -> str:
    """Select the first city suggestion from the search dropdown that appeared
    after enter_weather_forecast_city_israel was called, and navigate to that
    city's forecast page.
    """
    page = await _ensure_page()

    try:
        item = page.locator(DROPDOWN_ITEM_SELECTOR).first
        await item.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
        await item.click()
        # Wait for the resulting city forecast page to settle.
        await page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
        await page.wait_for_timeout(500)
    except PlaywrightTimeout:
        return (
            f"Could not find/click a dropdown suggestion using selector "
            f"'{DROPDOWN_ITEM_SELECTOR}'. The site's markup may differ - "
            f"see the SELECTORS note at the top of weather_Israel.py."
        )

    return f"Navigated to forecast page: {page.url}"


@mcp.tool()
async def get_weather_forecast_content_israel() -> str:
    """Extract and clean the text content of the currently open forecast page,
    so the LLM can read the forecast directly and answer the user's question
    without the user needing to look at the browser themselves.
    """
    page = await _ensure_page()

    try:
        locator = page.locator(FORECAST_CONTENT_SELECTOR).first
        raw_text = await locator.inner_text(timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightTimeout:
        # Fall back to the whole page body if the specific selector fails.
        raw_text = await page.locator("body").inner_text()

    cleaned = _clean_text(raw_text)

    if not cleaned:
        return "The page loaded but no readable forecast text was found."

    # Keep the payload reasonable for the model's context window.
    max_chars = 6000
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n...[truncated]"

    return cleaned


def _clean_text(text: str) -> str:
    """Collapse excess whitespace/blank lines from raw innerText."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


async def _close_browser() -> None:
    browser = _state.get("browser")
    playwright = _state.get("playwright")

    if browser is not None:
        try:
            await browser.close()  # type: ignore[union-attr]
        except Exception:
            pass
    if playwright is not None:
        try:
            await playwright.stop()  # type: ignore[union-attr]
        except Exception:
            pass

    _state["playwright"] = None
    _state["browser"] = None
    _state["page"] = None


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
