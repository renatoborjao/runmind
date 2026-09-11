from app.application.coach.writer.race_prediction_writer import (
    RacePredictionWriter,
)
from app.domain.entities.race_prediction import RacePrediction
from app.infrastructure.integrations.garmin.garmin_health_source import (
    GarminHealthSource,
)

# tempos reais do Garmin do renato2 (2026-09-10)
_REAL = RacePrediction(
    date="2026-09-10",
    time_5k_sec=1453, time_10k_sec=3086,
    time_half_sec=7064, time_marathon_sec=15569,
)


def test_formats_times_minutes_and_hours():
    # abaixo de 1h em M:SS; acima em H:MM:SS
    assert _REAL.time_5k == "24:13"
    assert _REAL.time_10k == "51:26"
    assert _REAL.time_half == "1:57:44"
    assert _REAL.time_marathon == "4:19:29"


def test_block_lists_available_distances():

    block = RacePredictionWriter.block(_REAL)

    assert "10K 51:26" in block
    assert "5K 24:13" in block
    assert "42K 4:19:29" in block
    assert "🏁" in block


def test_block_none_without_data():

    assert RacePredictionWriter.block(None) is None
    assert RacePredictionWriter.block(RacePrediction()) is None


def test_block_omits_missing_distances():
    # só 5K e 10K (device sem projeção de meia/maratona)
    partial = RacePrediction(time_5k_sec=1453, time_10k_sec=3086)

    block = RacePredictionWriter.block(partial)

    assert "5K 24:13" in block
    assert "10K 51:26" in block
    assert "21K" not in block
    assert "42K" not in block


def test_line_prioritizes_10k():

    assert RacePredictionWriter.line(_REAL) == "10K ~51:26 (Garmin)"
    # sem 10K, cai pro 5K
    assert RacePredictionWriter.line(
        RacePrediction(time_5k_sec=1453)
    ) == "5K ~24:13 (Garmin)"


def test_source_extracts_from_garmin_payload():
    # o shape real de get_race_predictions
    payload = {
        "calendarDate": "2026-09-10", "time5K": 1453, "time10K": 3086,
        "timeHalfMarathon": 7064, "timeMarathon": 15569,
    }

    pred = GarminHealthSource._extract_race_predictions(payload)

    assert pred.time_10k_sec == 3086
    assert pred.date == "2026-09-10"
    assert pred.has_data

    # payload torto/vazio não quebra
    assert not GarminHealthSource._extract_race_predictions(None).has_data
    assert not GarminHealthSource._extract_race_predictions([]).has_data
