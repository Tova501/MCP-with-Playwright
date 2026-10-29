"""
MCP Server: weather-Israel
Fetches Israeli weather forecasts by driving a real browser (Playwright)
against https://www.weather2day.co.il/forecast instead of calling an API.

This file is only the MCP layer: each tool is a thin wrapper that calls one
method of WeatherSiteBrowser (see weather_site_browser.py, where all the
Playwright code lives) and turns the result into a message for the LLM.

Tools exposed:
    1. open_weather_forecast_israel        - opens the browser & navigates to the forecast page
    2. enter_weather_forecast_city_israel  - types a city name into the search box
    3. select_weather_forecast_city_israel - clicks the first item in the autocomplete dropdown
    4. get_weather_forecast_content_israel - extracts & cleans the resulting page's text (RAG)
    5. close_weather_forecast_israel       - closes the browser when done
"""

from mcp.server.fastmcp import FastMCP

from weather_site_browser import WeatherSiteBrowser, WeatherSiteError

mcp = FastMCP("weather-Israel")
browser = WeatherSiteBrowser()


@mcp.tool()
async def open_weather_forecast_israel() -> str:
    """Open a browser and navigate to the Israeli weather forecast website
    (weather2day.co.il/forecast). Call this first, before searching for a city.
    """
    try:
        url = await browser.open()
    except WeatherSiteError as e:
        return str(e)
    return f"Opened {url}. Next: call enter_weather_forecast_city_israel."


@mcp.tool()
async def enter_weather_forecast_city_israel(city: str) -> str:
    """Type a city name into the forecast website's search field.

    Args:
        city: The name of the Israeli city to search for. Prefer Hebrew,
              e.g. "תל אביב", "חיפה", "באר שבע".
    """
    try:
        suggestions = await browser.type_city(city)
    except WeatherSiteError as e:
        return str(e)
    return (
        f"Typed '{city}'. Suggestions: {', '.join(suggestions[:5])}. "
        f"Next: call select_weather_forecast_city_israel."
    )


@mcp.tool()
async def select_weather_forecast_city_israel() -> str:
    """Select the first city suggestion from the search dropdown that appeared
    after enter_weather_forecast_city_israel was called, and navigate to that
    city's forecast page.
    """
    try:
        chosen, url = await browser.pick_first_suggestion()
    except WeatherSiteError as e:
        return str(e)
    return (
        f"Selected '{chosen}'. Forecast page: {url}. "
        f"Next: call get_weather_forecast_content_israel to read it."
    )


@mcp.tool()
async def get_weather_forecast_content_israel() -> str:
    """Extract and clean the text content of the currently open forecast page,
    so the LLM can read the forecast directly and answer the user's question
    without the user needing to look at the browser themselves.
    """
    try:
        text = await browser.read_forecast_text()
    except WeatherSiteError as e:
        return str(e)
    if not text:
        return "The page loaded but no readable forecast text was found."
    return f"Forecast page for '{browser.city or 'unknown city'}' ({browser.current_url}):\n{text}"


@mcp.tool()
async def close_weather_forecast_israel() -> str:
    """Close the browser opened by open_weather_forecast_israel. Call this
    after the forecast content was read and the user's question answered."""
    await browser.close()
    return "Browser closed."


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
