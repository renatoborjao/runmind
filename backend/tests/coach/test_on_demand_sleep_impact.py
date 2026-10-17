"""O cartão de sono sob demanda traz o custo do sono no desempenho. O analisador
foi renomeado (analyze -> assess) e a chamada antiga quebrava calada (best-effort
engole o erro) — este teste trava o contrato."""

import asyncio

from app.application.coach.conversation.on_demand_answers import OnDemandAnswers
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.history.sleep_performance_analyzer import (
    SleepPerformanceAnalyzer,
)


def test_sleep_impact_uses_assess_with_the_dossier_inputs(monkeypatch):

    seen = {}

    monkeypatch.setattr(
        FitnessReadingService,
        "_load",
        staticmethod(lambda profile: (["act"], ["serie"], 52, 188)),
    )

    def fake_assess(activities, health, resting_hr=None, max_hr=None, **kw):

        seen["args"] = (activities, health, resting_hr, max_hr)

        return "leitura"

    monkeypatch.setattr(
        SleepPerformanceAnalyzer, "assess", staticmethod(fake_assess)
    )

    result = asyncio.run(OnDemandAnswers._sleep_impact("renato2"))

    assert result == "leitura"

    assert seen["args"] == (["act"], ["serie"], 52, 188)
