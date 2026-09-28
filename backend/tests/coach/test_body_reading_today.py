"""Leitura do corpo que fala do DIA (Renato 28/09: acordou com bateria 87,
sono 8h31 nota 92, FC de repouso 57 — e o app seguia "Dá pra treinar, com
cautela", com a leitura escrita às 03:16 com a noite anterior e "FC repouso 57
(subindo)" nos fatos)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
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
    assert "NÃO abra pela" in _SYSTEM_PROMPT


def test_cached_reading_is_rewritten_when_the_night_arrives():

    reading = _reading()
    rec = reading.recovery
    same = SimpleNamespace(
        body_state=reading.body_state, limiter=reading.limiter,
        hrv_recent=rec.hrv_recent, rhr_recent=rec.rhr_recent,
        sleep_avg_hours=rec.sleep_avg_hours, short_nights=rec.short_nights,
    )

    assert BodyReadingService._same_basis(same, reading)

    before_the_night = SimpleNamespace(**{**vars(same), "rhr_recent": 67.0})

    assert not BodyReadingService._same_basis(before_the_night, reading)


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
