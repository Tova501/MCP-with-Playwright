# MCP with Playwright — Israeli Weather Forecast

An MCP server that gives an LLM the ability to control a real browser
(via [Playwright](https://playwright.dev/)) and fetch weather forecasts for
Israeli cities from [weather2day.co.il](https://www.weather2day.co.il/forecast),
instead of calling a conventional weather API.

This project is the Israeli counterpart to the bundled `weather_USA.py` demo
(which calls the US National Weather Service API). Here, the "API" is a
human user's browsing flow, automated end-to-end.

## How it works

1. **`open_weather_forecast_israel`** — opens a Chromium browser and
   navigates to `https://www.weather2day.co.il/forecast`.
2. **`enter_weather_forecast_city_israel`** — types the requested city name
   into the site's search box, triggering its autocomplete dropdown.
3. **`select_weather_forecast_city_israel`** — clicks the first suggestion in
   the dropdown, which navigates to that city's forecast page.
4. **`get_weather_forecast_content_israel`** — extracts the visible text of
   the resulting page, cleans it up, and hands it back to the LLM as context
   (RAG), so the LLM can answer the user's question directly in the chat
   instead of just leaving the browser open on the page. Menus, ads, scripts
   and footers are removed from the DOM before the text is read.
5. **`close_weather_forecast_israel`** — closes the browser when done.

The LLM (via `host.py`) decides on its own, based on the user's question,
which of these tools to call and in what order. Each tool's reply tells the
LLM which tool to call next, and if a step is skipped the server opens the
browser by itself instead of failing.

### Design: two layers

```
LLM ──► MCP tools (thin wrappers) ──► WeatherSiteBrowser (all Playwright code)
```

- **`WeatherSiteBrowser`** owns the single browser tab and every interaction
  with the site (selectors, waits, text cleaning). It knows nothing about MCP
  and can be used from a plain Python script.
- **The MCP tools** each call one browser method and turn the result (or a
  `WeatherSiteError`) into a message for the LLM.

If the site's markup changes, only the browser class needs fixing.

## Project structure

```
.
├── src/
│   ├── client.py               # Generic MCP client (provided)
│   ├── host.py                 # Terminal chat loop that wires everything together
│   ├── weather_USA.py          # US forecast MCP server (provided, via NWS API)
│   ├── weather_Israel.py       # ← MCP server: thin tool wrappers
│   └── weather_site_browser.py # ← WeatherSiteBrowser: all Playwright code for the site
├── tests/
│   ├── fixtures/               # Offline copy of the search + forecast pages
│   ├── conftest.py             # Shared fixture: browser pointed at the offline site
│   ├── test_clean_text.py      # Text cleaning (pure unit tests)
│   ├── test_weather_site_browser.py # Browser class vs. the offline site
│   ├── test_tools.py           # MCP tools with a fake browser
│   └── test_live_site.py       # End-to-end vs. the real site (skipped by default)
├── pyproject.toml
├── uv.lock
├── .env.example
└── README.md
```

## Setup

1. Install dependencies:
   ```bash
   uv sync
   ```
2. Install the Chromium browser for Playwright:
   ```bash
   uv run playwright install chromium
   ```
3. Copy `.env.example` to `.env` and fill in your `GOOGLE_API_KEY`.
4. Run the chat host:
   ```bash
   uv run src/host.py
   ```

## Tests

```bash
uv run pytest              # unit + offline browser tests (no internet needed)
uv run pytest -m live -s   # end-to-end against the real weather2day.co.il
```

The offline tests drive a real headless Chromium against the small HTML pages
in `tests/fixtures/`, so they check the Playwright logic without depending on
the live site. If the live test fails while the offline ones pass, the site's
markup changed — update the selectors (see below).

## ⚠️ If a tool call fails / selectors need tuning

`weather2day.co.il`'s exact HTML (class names, ids) can change, and the
autocomplete widget is rendered dynamically by JavaScript. The 3 CSS
selectors used in `weather_site_browser.py` (search input, dropdown item, forecast
content container) are class attributes of `WeatherSiteBrowser`:

```python
SEARCH_INPUT = "..."
SUGGESTION_ITEM = "..."
CONTENT = "..."
```

If a tool call times out, the fastest fix is to record the real selectors
yourself:

```bash
uv run playwright codegen https://www.weather2day.co.il/forecast
```

This opens a browser + Inspector panel. Click into the city search field and
select a city manually — Playwright will show you the exact selector/action
it recorded in the Inspector. Copy the corrected selector into the
matching attribute of `WeatherSiteBrowser` in `weather_site_browser.py`.

## Example questions to ask the Agent

- "מה התחזית להיום בתל אביב?"
- "האם צפוי גשם בחיפה השבוע?"
- "מה הטמפרטורה הצפויה בירושלים מחר?"
- "יש התראות מזג אוויר בבאר שבע?"
- (English also works) "What's the weather like in Eilat right now?"

The agent will pick the `weather-Israel` MCP server for Israeli cities and
the `weather-USA` MCP server for US states/coordinates.

## Notes

- The browser is **visible** by default so you can watch it work. Set
  `WEATHER_HEADLESS=1` in `.env` to run it without a window.
- `WEATHER_MAX_CHARS` (default 6000) limits how much page text is sent to the LLM.
- Each call to `open_weather_forecast_israel` closes any previously-open
  browser session first, so re-asking a new question starts clean.
