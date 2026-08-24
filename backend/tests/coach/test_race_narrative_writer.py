from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.coach.writer.race_narrative_writer import (
    RaceNarrativeWriter,
)
from app.domain.entities.training_goal import TrainingGoal

MODULE = "app.application.coach.writer.race_narrative_writer"


def _goal(target_time="00:55:00"):
    return TrainingGoal(
        name="10 km", distance_km=10.0,
        target_time=target_time, race_date=date(2026, 8, 23),
    )


def _enriched(negative=True):
    splits = (
        [5.98, 5.43, 5.35, 5.5, 5.23, 5.51, 5.51, 5.43, 5.33, 5.08]
        if negative
        else [5.0, 5.1, 5.2, 5.4, 5.6, 5.8, 6.0, 6.2, 6.4, 6.6]
    )
    return SimpleNamespace(
        activity=SimpleNamespace(
            distance=10030.0,
            moving_time=3258,
            start_date=datetime(2026, 8, 23, 8, 0),
            average_heartrate=146.0,
            max_heartrate=158.0,
        ),
        structure=SimpleNamespace(cadence_spm=170, km_splits=splits, km_hr=[]),
    )


def _facts(**kw):
    with (
        patch(f"{MODULE}.GarminHealthRepository") as gh,
        patch(f"{MODULE}.RunnerMemoryRepository") as mem,
    ):
        gh.return_value.load.return_value = kw.get("health", [])
        mem.return_value.active.return_value = kw.get("memory", [])
        return RaceNarrativeWriter._facts(
            "renato2",
            SimpleNamespace(name="Renato"),
            kw.get("enriched", _enriched()),
            kw.get("goal", _goal()),
        )


def test_facts_include_result_verdict_and_numbers():

    facts = _facts()

    assert "Distância: 10.03 km" in facts
    assert "Tempo: 54:18" in facts
    assert "Pace médio: 5:25/km" in facts
    assert "BATEU a meta de 55:00" in facts
    assert "FC média: 146 (máx 158) bpm" in facts
    assert "Cadência: 170 ppm" in facts


def test_facts_detect_negative_split():

    assert "negative split" in _facts(enriched=_enriched(negative=True))
    assert "caiu de ritmo no fim" in _facts(enriched=_enriched(negative=False))


def test_facts_pick_up_short_sleep_and_illness():

    health = [SimpleNamespace(date="2026-08-23", sleep_hours=4.3)]
    memory = [
        SimpleNamespace(
            category="vida",
            content="Sintomas de gripe com bastante catarro",
        ),
        SimpleNamespace(category="preferencia", content="gosta de correr cedo"),
    ]

    facts = _facts(health=health, memory=memory)

    assert "CONTEXTO ADVERSO" in facts
    assert "dormiu só 4.3h" in facts
    assert "gripe" in facts
    # preferência não é contexto adverso
    assert "correr cedo" not in facts


def test_facts_include_why_when_present():

    memory = [
        SimpleNamespace(category="motivacao", content="corre pela saúde do filho"),
    ]

    facts = _facts(memory=memory)

    assert "PORQUÊ DELE: corre pela saúde do filho" in facts


def test_facts_without_target_says_conclude():

    facts = _facts(goal=_goal(target_time=None))

    assert "sem tempo-alvo" in facts


def test_parse_valid_and_invalid():

    assert RaceNarrativeWriter._parse('{"narrative": "Que prova!"}') == "Que prova!"
    assert RaceNarrativeWriter._parse('{"narrative": "  "}') is None
    assert RaceNarrativeWriter._parse("lixo{") is None
    assert RaceNarrativeWriter._parse('{"outro": "x"}') is None


def test_is_health_complaint():

    assert RaceNarrativeWriter._is_health_complaint("gripe forte") is True
    assert RaceNarrativeWriter._is_health_complaint("dor no joelho") is True
    assert RaceNarrativeWriter._is_health_complaint("viagem a trabalho") is False
