import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.writer.ai_analysis_writer import (
    AIAnalysisWriter,
)
from app.domain.entities.workout_structure import WorkoutStructure
from tests.coach.factories import (
    make_context,
    make_enriched_activity,
)

MODULE = "app.application.coach.writer.ai_analysis_writer"


def _structure(**overrides) -> WorkoutStructure:

    defaults = dict(
        km_splits=[4.0, 6.5, 4.0, 6.5],
        km_hr=[172, 150, 174, 151],
        lap_count=0,
        lap_paces=[],
        fastest_km_pace=4.0,
        slowest_km_pace=6.5,
        pace_spread=0.625,
        split_trend="even",
        is_interval=True,
        cadence_spm=178,
        hr_avg=160,
        hr_max=182,
        has_detail=True,
    )

    defaults.update(overrides)

    return WorkoutStructure(**defaults)


def _write(context=None, **patch_kwargs):

    with patch(f"{MODULE}.generate_text", new=AsyncMock(**patch_kwargs)):

        return asyncio.run(
            AIAnalysisWriter.write(context or make_context())
        )


def test_returns_bullets_from_ai():

    lines = _write(
        return_value='{"analysis": ["Belo intervalado.", "Segurou os tiros."]}',
    )

    assert lines == ["Belo intervalado.", "Segurou os tiros."]


def test_returns_none_when_ai_fails():

    lines = _write(side_effect=RuntimeError("Gemini fora do ar"))

    assert lines is None


def test_returns_none_on_empty_analysis():

    lines = _write(return_value='{"analysis": []}')

    assert lines is None


def test_caps_at_max_bullets():

    lines = _write(
        return_value='{"analysis": ["a", "b", "c", "d", "e", "f"]}',
    )

    assert len(lines) == 4


def test_facts_feed_splits_and_interval_to_prompt():

    executed = make_enriched_activity(structure=_structure())

    context = make_context(executed=executed)

    mock = AsyncMock(return_value='{"analysis": ["ok"]}')

    with patch(f"{MODULE}.generate_text", new=mock):

        asyncio.run(AIAnalysisWriter.write(context))

    prompt = mock.await_args.kwargs["contents"]

    assert "splits:" in prompt
    assert "intervalado" in prompt
    # pace + FC por km: sem a FC a IA inventava "fadiga" em treino com
    # FC caindo na segunda metade
    assert "km1 4:00 (172bpm)" in prompt


def test_mild_fade_fact_has_no_verdict():
    """Bug do Renato: 2ª metade ~5% mais lenta chegava pra IA como
    "apagou" e virava "você quebrou" na análise."""

    executed = make_enriched_activity(
        structure=_structure(
            is_interval=False,
            split_trend="positive_mild",
        ),
    )

    context = make_context(executed=executed)

    mock = AsyncMock(return_value='{"analysis": ["ok"]}')

    with patch(f"{MODULE}.generate_text", new=mock):

        asyncio.run(AIAnalysisWriter.write(context))

    prompt = mock.await_args.kwargs["contents"]

    # o FATO é neutro ("variação normal"), não um veredito de quebra
    facts = prompt.split("REGRAS:")[0]

    assert "variação normal" in facts
    assert "apagou" not in facts
    assert "queda acentuada" not in facts


# ---- campos ricos do Garmin alimentando a IA (de acordo com o executado) ----

FULL_GARMIN = {
    "training_effect": 5.0, "training_effect_label": "LACTATE_THRESHOLD",
    "aerobic_effect_msg": "OVERREACHING_14",
    "anaerobic_effect": 0.0, "anaerobic_effect_msg": "NO_ANAEROBIC_BENEFIT_0",
    "workout_rpe": 50, "workout_feel": 75, "grade_adjusted_speed": 2.619,
    "ground_contact_ms": 284, "stride_length_cm": 97,
    "vertical_oscillation_cm": 8.7, "vertical_ratio": 9.0,
    "avg_power": 328, "normalized_power": 330, "max_power": 436,
    "body_battery_delta": -18, "vigorous_minutes": 76, "moderate_minutes": 1,
    "calories": 1176, "avg_temperature": 19.4, "max_temperature": 22,
}


def test_garmin_facts_none_without_metrics():

    assert AIAnalysisWriter._garmin_facts(None) is None
    assert AIAnalysisWriter._garmin_facts({}) is None


def test_clean_msg_strips_garmin_code_suffix():

    assert AIAnalysisWriter._clean_msg("OVERREACHING_14") == "overreaching"
    assert AIAnalysisWriter._clean_msg("NO_ANAEROBIC_BENEFIT_0") == (
        "no anaerobic benefit"
    )
    assert AIAnalysisWriter._clean_msg(None) is None


def test_garmin_facts_render_everything_meaningful():

    facts = AIAnalysisWriter._garmin_facts(FULL_GARMIN)

    assert "efeito aeróbico 5.0/5 (LACTATE_THRESHOLD / overreaching)" in facts
    assert "efeito anaeróbico 0.0/5 (no anaerobic benefit)" in facts
    assert "esforço percebido (RPE) 5/10" in facts
    assert "sensação do atleta: bem" in facts
    assert "pace ajustado ao relevo" in facts
    assert "contato com o solo 284 ms" in facts
    assert "razão vertical 9.0%" in facts
    assert "potência média 328 W (normalizada 330 W, máx 436 W)" in facts
    assert "body battery -18" in facts
    assert "76 vigorosos + 1 moderados" in facts
    assert "1176 kcal" in facts
    assert "temperatura ~19°C (máx 22°C)" in facts


def test_garmin_facts_omit_absent_fields():

    facts = AIAnalysisWriter._garmin_facts(
        {"training_effect": 3.0, "workout_feel": 50}
    )

    assert "efeito aeróbico 3.0/5" in facts
    assert "sensação do atleta: normal" in facts
    assert "potência" not in facts
    assert "body battery" not in facts
    assert "dinâmica" not in facts
