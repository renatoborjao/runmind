import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.intelligence.race_debrief import RaceDebrief
from tests.coach.factories import make_runner

MODULE = "app.application.coach.intelligence.race_debrief"

RACE_DAY = date(2026, 8, 23)


def _runner(target_time="00:50:00", race_date="2026-08-23"):
    return make_runner(
        target_race="10 km", target_time=target_time, race_date=race_date,
    )


def _activity(distance_m=10000.0, moving_sec=2940, day=RACE_DAY):
    """enriched.activity com os campos que o debrief lê."""
    return SimpleNamespace(
        activity=SimpleNamespace(
            distance=distance_m,
            moving_time=moving_sec,
            start_date=datetime(day.year, day.month, day.day, 8, 0),
        )
    )


def _rich_activity(day=RACE_DAY):
    """enriched com FC, cadência e parciais — o relatório completo da prova."""
    return SimpleNamespace(
        activity=SimpleNamespace(
            distance=10030.0,
            moving_time=3258,  # 54:18
            start_date=datetime(day.year, day.month, day.day, 8, 0),
            average_heartrate=146.0,
            max_heartrate=158.0,
        ),
        structure=SimpleNamespace(
            cadence_spm=170,
            km_splits=[5.983, 5.433, 5.35, 5.5, 5.233,
                       5.517, 5.517, 5.433, 5.333, 5.083],
            km_hr=[134, 142, 149, 144, 147, 151, 152, 145, 144, 152],
        ),
    )


def _run(runner, enriched, narrative=None):
    with (
        patch(f"{MODULE}.RunnerProfileRepository") as repo_cls,
        patch(f"{MODULE}.RaceResultRepository") as result_cls,
        patch(
            f"{MODULE}.RaceNarrativeWriter.write",
            new=AsyncMock(return_value=narrative),
        ),
    ):
        repo = MagicMock()
        repo_cls.return_value = repo
        result_repo = MagicMock()
        result_cls.return_value = result_repo
        reply = asyncio.run(
            RaceDebrief.after_feedback("renato2", runner, enriched)
        )
        _run.last_result_repo = result_repo
        return reply, repo


def test_beat_target_celebrates_and_clears_race_date():

    # 48:00 < meta 50:00
    reply, repo = _run(_runner(), _activity(moving_sec=2880))

    assert reply is not None
    assert "BATEU" in reply or "CONSEGUIU" in reply
    assert "48:00" in reply
    # aposenta o alvo concreto da prova cumprida (data + distância + tempo),
    # pra a projeção não seguir mirando uma prova que já aconteceu
    repo.update_fields.assert_called_once_with(
        "renato2",
        {"race_date": None, "target_race": None, "target_time": None},
    )


def test_near_miss_is_encouraging():

    # 50:30 -> dentro de 2% de 50:00
    reply, _ = _run(_runner(), _activity(moving_sec=3030))

    assert reply is not None
    assert "pertíssimo" in reply


def test_missed_target_is_honest():

    # 55:00 > meta 50:00 (fora da margem)
    reply, _ = _run(_runner(), _activity(moving_sec=3300))

    assert reply is not None
    assert "não saiu" in reply.lower()


def test_not_the_race_when_distance_off():

    # 5 km num dia de prova de 10 km -> não é a prova
    reply, repo = _run(_runner(), _activity(distance_m=5000.0))

    assert reply is None
    repo.update_fields.assert_not_called()


def test_no_race_date_returns_none():

    reply, repo = _run(_runner(race_date=None), _activity())

    assert reply is None
    repo.update_fields.assert_not_called()


def test_finish_without_target_still_celebrates():

    reply, repo = _run(_runner(target_time=None), _activity())

    assert reply is not None
    assert "CRUZOU" in reply
    repo.update_fields.assert_called_once()


def test_report_includes_stats_and_splits():
    """A prova merece o RELATÓRIO: veredito + números do dia (FC/cadência) +
    parciais km a km — não é 'mais um treino' sem detalhe."""

    reply, _ = _run(_runner(target_time="00:55:00"), _rich_activity())

    assert reply is not None
    # veredito: 54:18 <= 55:00 -> bateu
    assert "BATEU" in reply or "CONSEGUIU" in reply
    # números do dia
    assert "10.0 km em *54:18*" in reply
    assert "pace médio 5:25/km" in reply
    assert "FC 146/158 bpm" in reply
    assert "cadência 170 ppm" in reply
    # parciais km a km
    assert "⏱️ Parciais por km" in reply
    assert "km 1: 5:59 min/km · 134 bpm" in reply
    assert "km 10: 5:05 min/km · 152 bpm" in reply


def test_records_race_result_for_the_weekly_review():
    """Ao reconhecer a prova, o debrief PERSISTE o resultado — é o que deixa o
    resumo semanal saber que houve prova (o race_date é consumido)."""

    reply, _ = _run(_runner(target_time="00:55:00"), _rich_activity())

    assert reply is not None

    _run.last_result_repo.record.assert_called_once()

    profile_arg, result = _run.last_result_repo.record.call_args.args

    assert profile_arg == "renato2"
    assert result["date"] == "2026-08-23"
    assert result["race_label"] == "10 km"
    assert result["time"] == "54:18"
    assert result["beat"] is True


def test_report_includes_ai_narrative_when_available():
    """A narrativa da IA (o calor) entra no relatório quando disponível; sem
    ela, o relatório sai só com veredito + números (nunca depende dela)."""

    narrative = "Monstro, Renato! Mesmo capengando, cravou o sub-55 no fim."

    reply, _ = _run(_runner(), _rich_activity(), narrative=narrative)

    assert narrative in reply

    # sem narrativa (IA fora do ar): relatório ainda completo, sem quebrar
    reply_none, _ = _run(_runner(), _rich_activity(), narrative=None)

    assert reply_none is not None
    assert "Parciais" in reply_none


def test_report_without_structure_omits_splits():
    """Esteira/sem stream: sem parciais, o relatório ainda sai (veredito +
    tempo), nunca quebra."""

    reply, _ = _run(_runner(), _activity(moving_sec=2880))

    assert reply is not None
    assert "Parciais" not in reply


def _is_target(runner, enriched):
    with patch(f"{MODULE}.RunnerProfileRepository"):
        return RaceDebrief.is_target_race(runner, enriched)


def test_is_target_race_true_for_the_race():

    assert _is_target(_runner(), _activity()) is True


def test_is_target_race_false_when_distance_off_or_no_race():

    assert _is_target(_runner(), _activity(distance_m=5000.0)) is False
    assert _is_target(_runner(race_date=None), _activity()) is False
    assert _is_target(_runner(), None) is False
