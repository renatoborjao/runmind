from app.application.planner.race_time_formatter import RaceTimeFormatter


def test_format_under_an_hour():

    assert RaceTimeFormatter.format(50 * 60 + 12) == "50:12"


def test_format_over_an_hour():

    assert RaceTimeFormatter.format(3 * 3600 + 45 * 60 + 5) == "3:45:05"


def test_format_rounds_fractional_seconds():

    assert RaceTimeFormatter.format(90.6) == "1:31"


def test_parse_hms_valid():

    assert RaceTimeFormatter.parse_hms("00:50:00") == 3000
    assert RaceTimeFormatter.parse_hms("03:45:05") == 13505


def test_parse_hms_invalid_or_missing_returns_none():

    assert RaceTimeFormatter.parse_hms(None) is None
    assert RaceTimeFormatter.parse_hms("") is None
    assert RaceTimeFormatter.parse_hms("lixo") is None
    assert RaceTimeFormatter.parse_hms("50:00") is None
