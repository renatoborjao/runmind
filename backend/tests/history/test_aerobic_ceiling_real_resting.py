"""Leve = abaixo do teto aeróbico, o MESMO número em todo lugar, com o repouso
REAL de hoje (Renato 28/09). Maurício: a config do relógio guardava repouso 74
(real 61) → teto 157, dentro da Z4 dele; e a análise cobrava Z3 que estava
abaixo do teto."""

from types import SimpleNamespace
from unittest.mock import patch

from app.application.history.training_patterns import TrainingPatterns

REST = "app.application.history.hr_zone_resolver.HrZoneResolver.resting_now"

WATCH = SimpleNamespace(max_hr=193, resting_hr=74)


def test_ceiling_uses_todays_real_resting_hr():

    with patch(REST, return_value=61):

        assert TrainingPatterns.ceiling_of(WATCH, "mauricio") == 153


def test_without_watch_health_it_falls_back_to_the_zones_resting():

    with patch(REST, return_value=None):

        assert TrainingPatterns.ceiling_of(WATCH, "helio") == 157

    assert TrainingPatterns.ceiling_of(None, "x") is None


def test_analysis_judges_easy_by_the_ceiling_not_the_zone_number():

    from app.application.coach.writer import ai_analysis_writer as w

    prompt = next(
        v for k, v in vars(w).items()
        if isinstance(v, str) and "O QUE LER NOS FATOS" in v
    )

    assert "não cobre Z3 abaixo do teto" in prompt
    assert "muito tempo em Z3+" not in prompt
