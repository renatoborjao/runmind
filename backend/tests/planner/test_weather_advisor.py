from app.application.planner.weather_advisor import WeatherAdvisor


def _forecast(temp_max, feels_max=None, rain_prob=0, temp_min=15):

    return {
        "temp_max": temp_max,
        "temp_min": temp_min,
        "feels_max": feels_max if feels_max is not None else temp_max,
        "rain_prob": rain_prob,
    }


def test_hot_day_advises_hydration():

    line = WeatherAdvisor.line(_forecast(33, rain_prob=10))

    assert "33°C" in line
    assert "quente" in line.lower()
    assert "hidrat" in line.lower()


def test_heat_uses_feels_like_when_higher():

    # termômetro ameno (28) mas sensação de 31 -> conselho de calor
    line = WeatherAdvisor.line(_forecast(28, feels_max=31, rain_prob=0))

    assert "quente" in line.lower()
    assert "sensação 31" in line


def test_rain_day_suggests_treadmill():

    line = WeatherAdvisor.line(_forecast(22, rain_prob=80))

    assert "80%" in line
    assert "chuva" in line.lower()
    assert "esteira" in line.lower()


def test_cold_day_advises_warmup():

    line = WeatherAdvisor.line(_forecast(9, rain_prob=0))

    assert "frio" in line.lower()
    assert "aquec" in line.lower()


def test_mild_day_is_encouraging():

    line = WeatherAdvisor.line(_forecast(21, rain_prob=10))

    assert "boas" in line.lower()


def test_feels_note_hidden_when_close_to_temp():

    line = WeatherAdvisor.line(_forecast(22, feels_max=23, rain_prob=0))

    assert "sensação" not in line
