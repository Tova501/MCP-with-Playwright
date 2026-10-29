from pathlib import Path

import pytest

from weather_site_browser import WeatherSiteBrowser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def fake_site_browser():
    """A real headless browser pointed at the offline copy of the site."""
    browser = WeatherSiteBrowser(headless=True, timeout_ms=3_000)
    browser.URL = (FIXTURES / "search.html").as_uri()
    yield browser
    await browser.close()
