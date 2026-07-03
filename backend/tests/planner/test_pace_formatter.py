from app.application.planner.pace_formatter import PaceFormatter


def test_formats_whole_minute():

    assert PaceFormatter.format(5.0) == "5:00"


def test_formats_fractional_seconds():

    assert PaceFormatter.format(5.5) == "5:30"


def test_rounds_seconds():

    assert PaceFormatter.format(4.999) == "5:00"


def test_carries_minute_when_seconds_round_to_sixty():

    # 5.9917 -> 5min + 0.9917*60 = 59.5s -> arredonda pra 60 -> vira 6:00
    assert PaceFormatter.format(5.9917) == "6:00"


def test_formats_low_pace():

    assert PaceFormatter.format(4.25) == "4:15"
