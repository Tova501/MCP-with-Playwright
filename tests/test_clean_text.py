from weather_site_browser import WeatherSiteBrowser

clean = WeatherSiteBrowser._clean_text


def test_collapses_whitespace_and_drops_empty_lines():
    assert clean("  יום   ראשון \n\n\t\n 24° ") == "יום ראשון\n24°"


def test_drops_back_to_back_duplicates():
    assert clean("24°\n24°\n24°\nמעונן") == "24°\nמעונן"


def test_keeps_non_adjacent_repeats():
    # The same temperature on two different days is real data.
    assert clean("ראשון\n24°\nשני\n24°") == "ראשון\n24°\nשני\n24°"


def test_empty_input():
    assert clean("") == ""
    assert clean("\n  \n") == ""
