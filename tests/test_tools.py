"""The MCP tool wrappers, with the browser replaced by a fake (no Playwright)."""

import pytest

import weather_Israel
from weather_site_browser import WeatherSiteError


class FakeBrowser:
    city = "חיפה"
    current_url = "https://site/forecast/haifa"

    def __init__(self, error: str | None = None, text: str = "תחזית"):
        self.error = error
        self.text = text
        self.closed = False

    def _fail_if_needed(self):
        if self.error:
            raise WeatherSiteError(self.error)

    async def open(self):
        self._fail_if_needed()
        return "https://site/forecast"

    async def type_city(self, city):
        self._fail_if_needed()
        return ["חיפה", "חיפה - נווה שאנן"]

    async def pick_first_suggestion(self):
        self._fail_if_needed()
        return "חיפה", self.current_url

    async def read_forecast_text(self):
        self._fail_if_needed()
        return self.text

    async def close(self):
        self.closed = True


@pytest.fixture
def fake(monkeypatch):
    browser = FakeBrowser()
    monkeypatch.setattr(weather_Israel, "browser", browser)
    return browser


async def test_open_points_to_next_step(fake):
    result = await weather_Israel.open_weather_forecast_israel()

    assert "https://site/forecast" in result
    assert "enter_weather_forecast_city_israel" in result


async def test_enter_lists_suggestions(fake):
    result = await weather_Israel.enter_weather_forecast_city_israel("חיפה")

    assert "חיפה, חיפה - נווה שאנן" in result
    assert "select_weather_forecast_city_israel" in result


async def test_select_reports_chosen_city(fake):
    result = await weather_Israel.select_weather_forecast_city_israel()

    assert "Selected 'חיפה'" in result
    assert fake.current_url in result


async def test_content_has_header_with_city_and_url(fake):
    result = await weather_Israel.get_weather_forecast_content_israel()

    assert result.startswith(f"Forecast page for 'חיפה' ({fake.current_url}):")
    assert result.endswith("תחזית")


async def test_content_empty_page(fake):
    fake.text = ""

    result = await weather_Israel.get_weather_forecast_content_israel()

    assert "no readable forecast text" in result


async def test_close_closes_browser(fake):
    assert await weather_Israel.close_weather_forecast_israel() == "Browser closed."
    assert fake.closed


@pytest.mark.parametrize(
    "tool, args",
    [
        (weather_Israel.open_weather_forecast_israel, ()),
        (weather_Israel.enter_weather_forecast_city_israel, ("חיפה",)),
        (weather_Israel.select_weather_forecast_city_israel, ()),
        (weather_Israel.get_weather_forecast_content_israel, ()),
    ],
)
async def test_errors_become_messages_for_the_llm(monkeypatch, tool, args):
    monkeypatch.setattr(weather_Israel, "browser", FakeBrowser(error="boom"))

    assert await tool(*args) == "boom"
