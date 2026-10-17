"""A auditoria do coach agrupa os erros ENGOLIDOS (best-effort: "... falhou p/
'atleta': motivo"). Linhas REAIS do journal da VM — a classe que deixou o cartão de
sono sem o custo por 7 semanas e o 404 do Leonardo repetir todo domingo."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[3] / "ops" / "coach_audit.py"

_spec = importlib.util.spec_from_file_location("coach_audit_under_test", _PATH)

audit = importlib.util.module_from_spec(_spec)

_spec.loader.exec_module(audit)

PREFIX = "Oct 11 22:01:55 instance20260729015234 uvicorn[934994]: "


def _streams_404(activity_id):

    return (
        f"{PREFIX}Forma-sob-fadiga ({activity_id}) falhou p/ 'leonardo': Client "
        "error '404 Not Found' for url 'https://www.strava.com/api/v3/activities/"
        f"{activity_id}/streams?keys=time%2Cdistance%2Ccadence'"
    )


def test_same_failure_with_different_ids_is_one_group_with_count_and_athlete():

    lines = [_streams_404(i) for i in (20130667731, 19446504323, 19221744909)]

    out = audit.group_swallowed_failures(lines)

    assert len(out) == 1
    assert out[0].startswith("⚠️ Forma-sob-fadiga (N) falhou: 3x (leonardo)")
    assert "Client error 'N Not Found'" in out[0]


def test_the_sleep_impact_contract_error_is_surfaced():
    """O erro que passou 7 semanas calado: 'has no attribute analyze'."""

    line = (
        "Oct 17 12:00:00 vm uvicorn[1]: Impacto do sono falhou p/ 'renato2': type "
        "object 'SleepPerformanceAnalyzer' has no attribute 'analyze'"
    )

    out = audit.group_swallowed_failures([line])

    assert out == [
        "⚠️ Impacto do sono falhou: 1x (renato2) — type object "
        "'SleepPerformanceAnalyzer' has no attribute 'analyze'"
    ]


def test_telegram_payloads_and_noise_are_ignored():

    lines = [
        PREFIX + "{'update_id': 386660724, 'message': {'text': 'o treino falhou'}}",
        PREFIX + '{"ok":true,"result":{"message_id":2392}}',
        PREFIX + "Direct use of automatic function calling (AFC) is not recommended",
        PREFIX + "INFO: 127.0.0.1 - GET /health 200",
    ]

    assert audit.group_swallowed_failures(lines) == []


def test_failures_without_an_athlete_are_grouped_too():

    lines = [
        PREFIX + "[memory] espelhar prova em RaceRepository falhou: disco cheio",
        PREFIX + "[memory] espelhar prova em RaceRepository falhou: disco cheio",
    ]

    out = audit.group_swallowed_failures(lines)

    assert out == ["⚠️ [memory] espelhar prova em RaceRepository falhou: 2x — disco cheio"]


def test_most_frequent_group_comes_first():

    lines = [
        PREFIX + "A coisa falhou p/ 'x': motivo um",
        PREFIX + "B coisa falhou p/ 'y': motivo dois",
        PREFIX + "B coisa falhou p/ 'z': motivo dois",
    ]

    out = audit.group_swallowed_failures(lines)

    assert out[0].startswith("⚠️ B coisa falhou: 2x (y, z)")
    assert out[1].startswith("⚠️ A coisa falhou: 1x (x)")
