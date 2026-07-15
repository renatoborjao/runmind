import pytest

from app.core import clock


@pytest.fixture(autouse=True)
def _reset_tz():
    """Contextvar é global no processo — reseta pro padrão após cada teste
    pra não vazar fuso pra outros testes."""

    yield

    clock.use_athlete_timezone(None)


def test_default_active_timezone_is_brazil():

    assert clock.active_timezone().key == "America/Sao_Paulo"


def test_use_athlete_timezone_switches_dates_to_that_zone():

    clock.use_athlete_timezone("Europe/Lisbon")

    assert clock.active_timezone().key == "Europe/Lisbon"
    assert clock.now_local().tzinfo.key == "Europe/Lisbon"


def test_none_or_empty_falls_back_to_default():

    clock.use_athlete_timezone("Europe/Lisbon")
    clock.use_athlete_timezone(None)

    assert clock.active_timezone().key == "America/Sao_Paulo"


def test_invalid_timezone_falls_back_to_default():

    clock.use_athlete_timezone("Not/AZone")

    assert clock.active_timezone().key == "America/Sao_Paulo"


def test_now_in_uses_the_given_zone_regardless_of_active():

    clock.use_athlete_timezone("America/Sao_Paulo")

    assert clock.now_in("Europe/Lisbon").tzinfo.key == "Europe/Lisbon"
    assert clock.now_in(None).tzinfo.key == "America/Sao_Paulo"
