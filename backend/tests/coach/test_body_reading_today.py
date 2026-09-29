"""Leitura do corpo que fala do DIA (Renato 28/09: acordou com bateria 87,
sono 8h31 nota 92, FC de repouso 57 — e o app seguia "Dá pra treinar, com
cautela", com a leitura escrita às 03:16 com a noite anterior e "FC repouso 57
(subindo)" nos fatos)."""

import asyncio
from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.domain.entities.body_reading import BODY_STRAINED
from app.infrastructure.persistence.body_reading_history_repository import (
    BodyReadingHistoryRepository,
)
from app.application.coach.writer.body_reading_writer import (
    _SYSTEM_PROMPT,
    BodyReadingWriter,
)
from app.domain.entities.daily_health import DailyHealth
from app.presentation.api.v1.body import _headline
from tests.coach.test_body_reading_writer import _reading

REPO = (
    "app.infrastructure.persistence.garmin_health_repository."
    "GarminHealthRepository.load"
)
TODAY = "app.core.clock.today_local"


def _night(day: str) -> DailyHealth:

    return DailyHealth(
        date=day, sleep_hours=8.51, sleep_score=92, body_battery_at_wake=87,
        hrv_last_night=62, resting_hr=57, stress_avg=16,
    )


def test_tonight_is_the_raw_night_separate_from_the_trend():

    with patch(REPO, return_value=[_night("2026-09-28")]), \
            patch(TODAY, return_value=date(2026, 9, 28)):

        line = BodyReadingWriter._tonight_facts("renato2")

    assert line == (
        "NOITE DE HOJE (28/09) — o dado do dia: sono 8h31 (nota 92), bateria "
        "ao acordar 87, HRV da noite 62, FC de repouso 57, stress 16."
    )


def test_night_not_in_yet_is_said_so():

    with patch(REPO, return_value=[_night("2026-09-27")]), \
            patch(TODAY, return_value=date(2026, 9, 28)):

        line = BodyReadingWriter._tonight_facts("renato2")

    assert line == "NOITE DE HOJE: ainda não chegou do relógio (último dado: 2026-09-27)."


def test_trend_line_does_not_glue_todays_number_to_the_weeks_direction():

    with patch.object(BodyReadingWriter, "_tonight_facts", return_value="NOITE"), \
            patch(
                "app.application.coach.context.athlete_dossier.AthleteDossier.render",
                return_value="",
            ):

        facts = BodyReadingWriter._facts(_reading(rhr_recent=57.0), "Renato", profile="r")

    trend = next(l for l in facts.splitlines() if l.startswith("Recuperação"))

    assert "TENDÊNCIA" in trend and "57" not in trend
    assert "NOITE" in facts.splitlines()


def test_prompt_leads_with_what_changed_and_titles_the_day():

    assert "TÍTULO DE HOJE" in _SYSTEM_PROMPT
    assert "HOJE × TENDÊNCIA" in _SYSTEM_PROMPT
    # a trajetória não abre a mensagem e é dita em TEMPO, nunca em "N leituras"
    assert "NÃO abra por ela" in _SYSTEM_PROMPT
    assert 'nunca em "N leituras seguidas"' in _SYSTEM_PROMPT


def test_prompt_celebrates_a_good_night_instead_of_dismissing_it():
    """Renato 28/09: noite ótima (8,5h, bateria 87) e o coach escreveu que ela
    'não apaga o padrão de 15 leituras' — invalidou a noite boa dele."""

    assert "BOA NOTÍCIA de verdade" in _SYSTEM_PROMPT
    assert 'jamais escreva que ela "não apaga"' in _SYSTEM_PROMPT


SVC = "app.application.coach.intelligence.body_reading_service"
D27, D28 = date(2026, 9, 27), date(2026, 9, 28)


def _snap(day: date, narrative, night, reading=None):

    return BodyReadingService.snapshot_of(
        reading or _reading(), datetime.combine(day, time(7)),
        narrative=narrative, night=night,
    )


def _narrate(tmp_path, snapshots, nights, today=D28, reading=None):
    """narrative_for com o histórico no tmp, as noites do relógio e a IA
    mockada. Devolve (texto, nº de chamadas à IA, snapshots gravados)."""

    tmp_path.mkdir(parents=True, exist_ok=True)

    repo = BodyReadingHistoryRepository()
    repo.storage = tmp_path

    for s in snapshots:
        repo.record("r", s)

    narrate = AsyncMock(return_value=("🩺 nova", True))

    with patch(f"{SVC}.BodyReadingHistoryRepository", lambda: repo), \
            patch(REPO, return_value=[_night(d) for d in nights]), \
            patch(f"{SVC}.BodyReadingWriter.narrate", new=narrate), \
            patch(f"{SVC}.now_local", return_value=datetime.combine(today, time(15))):

        text = asyncio.run(BodyReadingService.narrative_for(
            "r", "Renato", reading or _reading(), MagicMock(), reference_date=today,
        ))

    return text, narrate.await_count, repo.load("r")


def test_same_night_never_calls_the_ai_again(tmp_path):
    """FC de repouso recalculada à tarde (números mudam) não reescreve."""

    text, calls, _ = _narrate(
        tmp_path, [_snap(D28, "🩺 manhã", "2026-09-28")],
        ["2026-09-27", "2026-09-28"], reading=_reading(rhr_recent=55.0),
    )

    assert (text, calls) == ("🩺 manhã", 0)


def test_new_night_rewrites_once_and_remembers_the_night(tmp_path):

    text, calls, saved = _narrate(
        tmp_path, [_snap(D27, "🩺 ontem", "2026-09-27")],
        ["2026-09-27", "2026-09-28"],
    )

    assert (text, calls) == ("🩺 nova", 1)
    assert (saved[-1].day, saved[-1].night) == (D28, "2026-09-28")


def test_before_tonight_syncs_the_last_nights_reading_holds(tmp_path):

    text, calls, _ = _narrate(
        tmp_path, [_snap(D27, "🩺 ontem", "2026-09-27")], ["2026-09-27"],
    )

    assert (text, calls) == ("🩺 ontem", 0)


def test_no_sleep_in_the_watch_is_one_a_day(tmp_path):

    assert _narrate(tmp_path / "a", [_snap(D28, "🩺 hoje", None)], [])[:2] == ("🩺 hoje", 0)
    assert _narrate(tmp_path / "b", [_snap(D27, "🩺 ontem", None)], [])[:2] == ("🩺 nova", 1)


def test_todays_reading_from_before_this_rule_is_kept(tmp_path):
    """Deploy no meio do dia: a leitura de hoje sem a noite gravada vale."""

    text, calls, _ = _narrate(
        tmp_path, [_snap(D28, "🩺 hoje", None)], ["2026-09-28"],
    )

    assert (text, calls) == ("🩺 hoje", 0)


def test_rereading_the_body_keeps_the_nights_reading(tmp_path):
    """Chat/tick relendo o corpo com o estado mudado não apaga o cache."""

    from tests.coach.test_body_reading_service import _run

    repo = BodyReadingHistoryRepository()
    repo.storage = tmp_path
    repo.record("renato", _snap(D28, "🩺 manhã", "2026-09-28"))

    _run(tmp_path, _reading(body_state=BODY_STRAINED), D28)

    kept = repo.load("renato")[-1]

    assert (kept.narrative, kept.night, kept.body_state) == (
        "🩺 manhã", "2026-09-28", BODY_STRAINED,
    )


def test_home_title_and_note_come_from_the_coach():

    narrative = (
        "🩺 Acordou inteiro — dia livre pra descansar bem\n\n"
        "⚖️ A noite foi a melhor em semanas.\n\n❤️ sinais\n\n🎯 foco"
    )

    assert _headline(narrative) == (
        "Acordou inteiro — dia livre pra descansar bem",
        "A noite foi a melhor em semanas.",
    )
    # narrativa antiga/fallback: sem título do dia → a home usa a reserva
    assert _headline("🩺 Leitura do corpo\n\n⚖️ x")[0] is None
    assert _headline(None) == (None, None)


def test_today_in_the_plan_rest_day_is_said_so():
    """Segunda sem treino: a leitura não pode mandar "aproveite no treino"."""

    from app.domain.entities.planned_session import PlannedSession
    from app.domain.entities.training_plan import TrainingPlan

    plan = TrainingPlan(
        athlete_name="R", objective="x", phase="BUILD", weekly_volume=20,
        running_days=["Tuesday"], week_start=date(2026, 9, 28),
        sessions=[PlannedSession("Tuesday", "Limiar", "", 8.0, None, None, None)],
    )

    with patch(
        "app.infrastructure.persistence.weekly_plan_repository."
        "WeeklyPlanRepository.load", return_value=plan,
    ), patch(TODAY, return_value=date(2026, 9, 28)):

        rest = BodyReadingWriter._today_plan_facts("r")

    with patch(
        "app.infrastructure.persistence.weekly_plan_repository."
        "WeeklyPlanRepository.load", return_value=plan,
    ), patch(TODAY, return_value=date(2026, 9, 29)):

        run = BodyReadingWriter._today_plan_facts("r")

    assert rest == "HOJE (segunda-feira 28/09) no plano: sem treino — dia de descanso."
    assert run == "HOJE (terça-feira 29/09) no plano: Limiar."
