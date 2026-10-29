"""End-to-end check against the REAL weather2day.co.il (needs internet).

Skipped by default. Run it with:  uv run pytest -m live
Set WEATHER_HEADLESS=0 to watch the browser do it.
"""

import pytest

from weather_site_browser import WeatherSiteBrowser


@pytest.mark.live
async def test_haifa_forecast_from_real_site():
    browser = WeatherSiteBrowser()
    try:
        await browser.open()
        suggestions = await browser.type_city("חיפה")
        chosen, url = await browser.pick_first_suggestion()
        text = await browser.read_forecast_text()
    finally:
        await browser.close()

    print(f"\nSuggestions: {suggestions}\nChosen: {chosen} -> {url}\n\n{text[:1500]}")
    assert suggestions
    assert "חיפה" in chosen
    assert len(text) > 200
