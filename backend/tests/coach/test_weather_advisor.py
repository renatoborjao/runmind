from app.application.coach.intelligence.weather_advisor import WeatherAdvisor


def _hours(peak_feels, peak_hour=15, cool_feels=22, cool_hour=6):

    return [
        {"hour": cool_hour, "feels": cool_feels, "rain": 0},
        {"hour": 10, "feels": (peak_feels + cool_feels) / 2, "rain": 0},
        {"hour": peak_hour, "feels": peak_feels, "rain": 0},
    ]


def test_mild_day_gives_no_advice():

    assert WeatherAdvisor._build(_hours(24)) is None


def test_hot_day_advises_window_pace_and_hydration():

    out = WeatherAdvisor._build(_hours(33, peak_hour=15, cool_feels=23, cool_hour=6))

    assert out is not None
    assert "~33" in out          # pico
    assert "6h" in out           # janela mais fresca
    assert "hidrata" in out.lower()
    assert "s/km" in out         # ajuste de pace


def test_extreme_heat_warns_pace_is_unreliable():

    out = WeatherAdvisor._build(_hours(36))

    assert "20s/km+" in out
    assert "não cobre número" in out


def test_pace_caution_scales_with_heat():

    assert WeatherAdvisor._pace_caution(29)[0] == "~8-10s/km"
    assert WeatherAdvisor._pace_caution(32)[0] == "~12-18s/km"
    assert WeatherAdvisor._pace_caution(35)[0] == "~20s/km+"


def test_build_empty_when_no_valid_feels():

    assert WeatherAdvisor._build([{"hour": 8, "feels": None, "rain": 0}]) is None


def test_aviso_de_hoje_nao_sugere_hora_que_ja_passou():

    hours = [
        {"hour": 5, "feels": 22, "rain": 0},
        {"hour": 10, "feels": 30, "rain": 0},
        {"hour": 15, "feels": 34, "rain": 0},
        {"hour": 20, "feels": 26, "rain": 0},
    ]

    out = WeatherAdvisor._build(hours, now_hour=10)

    assert "~5h" not in out

    assert "fim do dia (~20h" in out

    # de manhã cedo, o horário fresco ainda vem pela frente
    assert "mais cedo (~5h" in WeatherAdvisor._build(hours, now_hour=4)


def test_sem_hora_fresca_pela_frente_nao_sugere_horario():

    hours = [
        {"hour": 5, "feels": 22, "rain": 0},
        {"hour": 14, "feels": 34, "rain": 0},
        {"hour": 16, "feels": 33, "rain": 0},
    ]

    out = WeatherAdvisor._build(hours, now_hour=13)

    assert "Se der" not in out

    assert "Segura o pace" in out
