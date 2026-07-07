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
    assert "km1 4:00" in prompt
