"""WeatherSiteBrowser against the offline fixture site (real Chromium, no network)."""

import pytest

from weather_site_browser import WeatherSiteError


async def test_open_loads_search_page(fake_site_browser):
    url = await fake_site_browser.open()

    assert fake_site_browser.is_open
    assert url.endswith("search.html")


async def test_type_city_returns_suggestions(fake_site_browser):
    await fake_site_browser.open()

    suggestions = await fake_site_browser.type_city("חיפה")

    assert suggestions == ["חיפה", "חיפה - נווה שאנן"]
    assert fake_site_browser.city == "חיפה"


async def test_type_city_opens_browser_if_needed(fake_site_browser):
    suggestions = await fake_site_browser.type_city("ירושלים")

    assert fake_site_browser.is_open
    assert suggestions == ["ירושלים"]


async def test_type_city_rejects_empty_name(fake_site_browser):
    with pytest.raises(WeatherSiteError, match="empty"):
        await fake_site_browser.type_city("   ")


async def test_type_city_unknown_city(fake_site_browser):
    await fake_site_browser.open()

    with pytest.raises(WeatherSiteError, match="no suggestions"):
        await fake_site_browser.type_city("עיר שלא קיימת")


async def test_pick_without_typing_fails(fake_site_browser):
    await fake_site_browser.open()

    with pytest.raises(WeatherSiteError, match="No suggestion list"):
        await fake_site_browser.pick_first_suggestion()


async def test_full_flow_reads_clean_forecast(fake_site_browser):
    await fake_site_browser.open()
    await fake_site_browser.type_city("חיפה")

    chosen, url = await fake_site_browser.pick_first_suggestion()
    text = await fake_site_browser.read_forecast_text()

    assert chosen == "חיפה"
    assert "forecast.html" in url
    assert text.splitlines() == ["תחזית חיפה", "יום ראשון", "24°", "יום שני", "מעונן חלקית", "24°"]
    for noise in ("תפריט ראשי", "קישורים מהירים", "פרסומת", "SHOULD_NOT_APPEAR", "כל הזכויות"):
        assert noise not in text


async def test_read_forecast_text_truncates(fake_site_browser):
    await fake_site_browser.open()
    await fake_site_browser.type_city("חיפה")
    await fake_site_browser.pick_first_suggestion()

    text = await fake_site_browser.read_forecast_text(max_chars=10)

    assert text.endswith("...[truncated]")
    assert len(text) == 10 + len("\n...[truncated]")


async def test_read_without_open_page_fails(fake_site_browser):
    with pytest.raises(WeatherSiteError, match="No forecast page"):
        await fake_site_browser.read_forecast_text()


async def test_close_is_idempotent(fake_site_browser):
    await fake_site_browser.open()

    await fake_site_browser.close()
    await fake_site_browser.close()

    assert not fake_site_browser.is_open
    assert fake_site_browser.current_url == ""
