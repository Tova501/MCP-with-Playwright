# MCP with Playwright — Israeli Weather Forecast

An MCP server that gives an LLM the ability to control a real browser
(via [Playwright](https://playwright.dev/)) and fetch weather forecasts for
Israeli cities from [weather2day.co.il](https://www.weather2day.co.il/forecast),
instead of calling a conventional weather API.

This project is the Israeli counterpart to the bundled `weather_USA.py` demo
(which calls the US National Weather Service API). Here, the "API" is a
human user's browsing flow, automated end-to-end.

## How it works

1. **`open_weather_forecast_israel`** — opens a headless Chromium browser and
   navigates to `https://www.weather2day.co.il/forecast`.
2. **`enter_weather_forecast_city_israel`** — types the requested city name
   into the site's search box, triggering its autocomplete dropdown.
3. **`select_weather_forecast_city_israel`** — clicks the first suggestion in
   the dropdown, which navigates to that city's forecast page.
4. **`get_weather_forecast_content_israel`** — extracts the visible text of
   the resulting page, cleans it up, and hands it back to the LLM as context
   (RAG), so the LLM can answer the user's question directly in the chat
   instead of just leaving the browser open on the page.

The LLM (via `host.py`) decides on its own, based on the user's question,
which of these 4 tools to call and in what order.

## Project structure

```
.
├── client.py            # Generic MCP client (provided)
├── host.py              # Terminal chat loop that wires everything together
├── weather_USA.py       # US forecast MCP server (provided, via NWS API)
├── weather_Israel.py    # ← This project: Israeli forecast MCP server (Playwright)
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
3. Copy `.env.example` to `.env` and fill in your `ANTHROPIC_API_KEY`.
4. Run the chat host:
   ```bash
   uv run host.py
   ```

## ⚠️ If a tool call fails / selectors need tuning

`weather2day.co.il`'s exact HTML (class names, ids) can change, and the
autocomplete widget is rendered dynamically by JavaScript. The 3 CSS
selectors used in `weather_Israel.py` (search input, dropdown item, forecast
content container) are defined as constants at the top of the file:

```python
SEARCH_INPUT_SELECTOR = "..."
DROPDOWN_ITEM_SELECTOR = "..."
FORECAST_CONTENT_SELECTOR = "..."
```

If a tool call times out, the fastest fix is to record the real selectors
yourself:

```bash
uv run playwright codegen https://www.weather2day.co.il/forecast
```

This opens a browser + Inspector panel. Click into the city search field and
select a city manually — Playwright will show you the exact selector/action
it recorded in the Inspector. Copy the corrected selector into the
matching constant in `weather_Israel.py`.

## Example questions to ask the Agent

- "מה התחזית להיום בתל אביב?"
- "האם צפוי גשם בחיפה השבוע?"
- "מה הטמפרטורה הצפויה בירושלים מחר?"
- "יש התראות מזג אוויר בבאר שבע?"
- (English also works) "What's the weather like in Eilat right now?"

The agent will pick the `weather-Israel` MCP server for Israeli cities and
the `weather-USA` MCP server for US states/coordinates.

## Notes

- The browser runs **headless** by default (no visible window). To watch it
  work while debugging, change `headless=True` to `headless=False` in
  `open_weather_forecast_israel`.
- Each call to `open_weather_forecast_israel` closes any previously-open
  browser session first, so re-asking a new question starts clean.
