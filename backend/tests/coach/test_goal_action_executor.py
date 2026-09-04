"""Validação OFFLINE do executor estruturado de metas/provas (flag goal_brain).

Cobre os 5 furos que a interação real do Renato expôs:
- prova mais DISTANTE não atropela a âncora mais próxima;
- degrau (stepping_stone) preserva o objetivo-mãe (norte);
- hierarquia vira memória;
- prova de conclusão (sem tempo-alvo) limpa o tempo herdado;
- regeração só dentro da janela que afeta a semana atual (senão domingo mira).
Ver [[project_multiplos_objetivos]]."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.coach_brain import BrainAction
from app.application.coach.conversation.goal_action_executor import (
    GoalActionExecutor,
)
from tests.coach.factories import make_runner

G = "app.application.coach.conversation.goal_action_executor"

TODAY = date(2026, 9, 3)


def _goal_action(**kw) -> BrainAction:
    base = dict(
        type="goal",
        scope="single_session",
        target_day=None,
        instruction="",
    )
    base.update(kw)
    return BrainAction(**base)


def _run(action, runner=None, say="", for_profile=None):
    """Roda o executor com memória/perfil/plano mockados. Devolve
    (reply, profile_repo, memory_mock, for_profile_mock)."""

    repo = MagicMock()

    memory = MagicMock()

    for_profile = for_profile or AsyncMock(
        return_value=(make_runner(), MagicMock())
    )

    ctx = [
        patch(f"{G}.RunnerProfileRepository", return_value=repo),
        patch(f"{G}.RunnerMemoryService.process", new=memory),
        patch(f"{G}.CurrentPlanProvider.for_profile", new=for_profile),
        patch(
            f"{G}.WeeklyPlanMessageFormatter.week_plan_message",
            return_value="🏃 PLANO DA SEMANA",
        ),
        patch(f"{G}.watch_update_offer", return_value="\n\n⌚ Quer no relógio?"),
        patch(f"{G}.today_local", return_value=TODAY),
    ]

    for c in ctx:
        c.start()

    try:
        reply = asyncio.run(
            GoalActionExecutor.apply(
                "renato", runner or make_runner(), action, say,
            )
        )
    finally:
        for c in reversed(ctx):
            c.stop()

    return reply, repo, memory, for_profile


def _run_many(actions, runner=None, say="", for_profile=None):
    """Como _run, mas exercita apply_many com VÁRIAS metas."""

    repo = MagicMock()
    memory = MagicMock()
    for_profile = for_profile or AsyncMock(
        return_value=(make_runner(), MagicMock())
    )

    ctx = [
        patch(f"{G}.RunnerProfileRepository", return_value=repo),
        patch(f"{G}.RunnerMemoryService.process", new=memory),
        patch(f"{G}.CurrentPlanProvider.for_profile", new=for_profile),
        patch(
            f"{G}.WeeklyPlanMessageFormatter.week_plan_message",
            return_value="🏃 PLANO DA SEMANA",
        ),
        patch(f"{G}.watch_update_offer", return_value="\n\n⌚ Quer no relógio?"),
        patch(f"{G}.today_local", return_value=TODAY),
    ]

    for c in ctx:
        c.start()

    try:
        reply = asyncio.run(
            GoalActionExecutor.apply_many(
                "renato", runner or make_runner(), actions, say,
            )
        )
    finally:
        for c in reversed(ctx):
            c.stop()

    return reply, repo, memory, for_profile


def _anchor_updates(repo) -> dict:
    """Junta todos os update_fields que tocaram a âncora (race_date)."""

    merged = {}

    for call in repo.update_fields.call_args_list:

        fields = call.args[1] if len(call.args) > 1 else call.kwargs.get("updates", {})

        if "race_date" in fields:

            merged.update(fields)

    return merged


def _all_updates(repo) -> dict:
    merged = {}
    for call in repo.update_fields.call_args_list:
        fields = call.args[1] if len(call.args) > 1 else call.kwargs.get("updates", {})
        merged.update(fields)
    return merged


# ---------------------------------------------------------------- casos

def test_nothing_actionable_returns_none():
    """Sem prova e sem texto de meta: deixa a fala do coach (None)."""

    reply, repo, _, _ = _run(_goal_action(instruction=""))

    assert reply is None
    repo.update_fields.assert_not_called()


def test_near_race_sets_anchor_and_regenerates():
    """Prova PERTO (dentro da janela) e sem âncora prévia: seta a âncora e
    regenera a semana agora, com plano + oferta de relógio."""

    action = _goal_action(
        instruction="correr a 10k do Ibira sub-50",
        race_name="10k do Ibirapuera",
        distance_km=10,
        race_date="2026-09-13",  # 10 dias
        target_time="00:50:00",
        relationship="primary",
    )

    for_profile = AsyncMock(return_value=(make_runner(), MagicMock()))

    reply, repo, memory, fp = _run(
        action, say="Bora, 10k marcada! 🎯", for_profile=for_profile,
    )

    anchor = _anchor_updates(repo)
    assert anchor["race_date"] == "2026-09-13"
    assert anchor["target_time"] == "00:50:00"
    assert "10k do Ibirapuera" in anchor["target_race"]
    fp.assert_awaited_once()  # regenerou
    assert reply.startswith("Bora, 10k marcada! 🎯")
    assert "🏃 PLANO DA SEMANA" in reply
    assert "relógio" in reply
    memory.assert_called_once()


def test_far_stepping_stone_sets_anchor_but_no_regen_and_keeps_north_star():
    """Caso REAL do Renato: 15k em dez como DEGRAU, sem âncora prévia. Vira
    âncora (é a mais próxima), MAS não regenera agora (fora da janela) e NÃO
    mexe no objetivo-mãe (norte). Domingo mira a prova."""

    action = _goal_action(
        instruction="correr a 15k Villa-Lobos em 5:00/km",
        race_name="Santander Track&Field - Villa-Lobos",
        distance_km=15,
        race_date="2026-12-20",  # ~108 dias
        target_time="1:15:00",
        relationship="stepping_stone",
    )

    reply, repo, memory, fp = _run(
        action, runner=make_runner(goal="correr 21 km com saúde"),
        say="Boa! Registrei tua 15k como degrau rumo aos 21k. 🎯",
    )

    anchor = _anchor_updates(repo)
    assert anchor["race_date"] == "2026-12-20"
    fp.assert_not_awaited()  # NÃO regenera no meio da semana
    # objetivo-mãe (norte) preservado: nenhum update tocou "goal"
    assert "goal" not in _all_updates(repo)
    assert reply == "Boa! Registrei tua 15k como degrau rumo aos 21k. 🎯"
    # a hierarquia foi pra memória
    mem_content = memory.call_args.args[1]["add"][0]["content"]
    assert "DEGRAU" in mem_content


def test_farther_race_does_not_overwrite_nearer_anchor():
    """O BUG central: com a 15k (dez/2026) já ancorada, dizer a meia (jul/2027)
    NÃO pode atropelar a âncora. A meia atualiza o NORTE (primary), mas a âncora
    segue na 15k mais próxima."""

    runner = make_runner(
        goal="correr 15k rápido",
        target_race="Villa-Lobos (15 km)",
        race_date="2026-12-20",
        target_time="1:15:00",
    )

    action = _goal_action(
        instruction="completar a meia maratona (Nike SP 2027)",
        race_name="Nike SP City Marathon",
        distance_km=21,
        race_date="2027-07-25",  # MAIS DISTANTE
        target_time=None,  # completar bem
        relationship="primary",
    )

    reply, repo, memory, fp = _run(
        action, runner=runner, say="Anotei tua meia como norte! 🎯",
    )

    # âncora NÃO mudou (nenhum update tocou race_date)
    assert "race_date" not in _all_updates(repo)
    # mas o NORTE foi atualizado (primary)
    assert _all_updates(repo).get("goal") == "completar a meia maratona (Nike SP 2027)"
    fp.assert_not_awaited()
    memory.assert_called_once()


def test_replace_forces_anchor_and_updates_north_star():
    """Troca explícita (replace): reancorar na prova nova mesmo que mais
    distante, e trocar o objetivo-mãe."""

    runner = make_runner(
        goal="10k rápido", target_race="10k", race_date="2026-09-20",
        target_time="00:48:00",
    )

    action = _goal_action(
        instruction="agora meu foco é a maratona",
        race_name="Maratona de SP",
        distance_km=42,
        race_date="2027-04-10",  # mais distante, mas é TROCA
        target_time=None,
        relationship="replace",
    )

    reply, repo, _, _ = _run(action, runner=runner, say="Bora pra maratona! 🎯")

    anchor = _anchor_updates(repo)
    assert anchor["race_date"] == "2027-04-10"  # reancorou mesmo mais longe
    assert anchor["target_time"] is None  # conclusão limpa o tempo herdado
    assert _all_updates(repo).get("goal") == "agora meu foco é a maratona"


def test_aspiration_replace_updates_goal_without_anchor():
    """Meta sem prova (aspiração): atualiza o objetivo e a memória, sem âncora
    e sem regeração."""

    action = _goal_action(
        instruction="emagrecer e correr com saúde",
        relationship="replace",
    )

    reply, repo, memory, fp = _run(action, say="Anotado, foco na saúde! 💪")

    updates = _all_updates(repo)
    assert updates.get("goal") == "emagrecer e correr com saúde"
    assert "race_date" not in updates
    fp.assert_not_awaited()
    assert reply == "Anotado, foco na saúde! 💪"
    memory.assert_called_once()


def test_external_coach_registers_but_never_regenerates():
    """Atleta de treinador externo: registra meta/prova mas NUNCA gera plano."""

    action = _goal_action(
        instruction="10k sub-50",
        race_name="10k",
        distance_km=10,
        race_date="2026-09-13",  # perto — mas é externo
        target_time="00:50:00",
        relationship="primary",
    )

    reply, repo, memory, fp = _run(
        action, runner=make_runner(external_coach=True), say="Anotado! 🎯",
    )

    fp.assert_not_awaited()  # externo nunca regenera
    assert reply == "Anotado! 🎯"
    memory.assert_called_once()


def test_past_race_is_not_set_as_anchor():
    """Prova cuja data já passou não vira âncora (mas ainda é registrada)."""

    action = _goal_action(
        instruction="corri a de ontem",
        race_name="Prova de ontem",
        distance_km=10,
        race_date="2026-09-01",  # antes de TODAY
        relationship="primary",
    )

    reply, repo, memory, _ = _run(action, say="Boa prova! 👏")

    assert "race_date" not in _all_updates(repo)
    memory.assert_called_once()


def test_two_races_one_message_anchor_is_nearest_order_independent():
    """Turno real: a meia (norte, mais LONGE) + a 15k (degrau, mais PERTO) na
    mesma mensagem, com a mais LONGE listada PRIMEIRO. A âncora final é a mais
    PRÓXIMA (15k) mesmo assim; o norte vira a meia. Independente da ordem."""

    meia = _goal_action(
        instruction="completar a meia (Nike SP 2027)",
        race_name="Nike SP", distance_km=21, race_date="2027-07-25",
        target_time=None, relationship="primary",
    )
    quinze = _goal_action(
        instruction="15k Villa-Lobos em 5:00/km",
        race_name="Villa-Lobos", distance_km=15, race_date="2026-12-20",
        target_time="1:15:00", relationship="stepping_stone",
    )

    reply, repo, memory, fp = _run_many(
        [meia, quinze],  # mais LONGE primeiro (ordem adversa)
        runner=make_runner(goal="correr com saúde"),
        say="A meia é o norte; a 15k é degrau. 🎯",
    )

    anchor = _anchor_updates(repo)
    assert anchor["race_date"] == "2026-12-20"  # a mais PRÓXIMA venceu
    assert _all_updates(repo).get("goal") == "completar a meia (Nike SP 2027)"
    fp.assert_not_awaited()  # ambas longe -> sem regeração agora
    assert memory.call_count == 2  # as duas provas registradas
    assert reply == "A meia é o norte; a 15k é degrau. 🎯"


def test_completion_race_clears_inherited_target_time():
    """Reancorar numa prova de CONCLUSÃO (sem tempo-alvo) limpa o tempo-alvo
    herdado da prova anterior (não prescreve pace de outra prova)."""

    runner = make_runner(
        target_race="10k", race_date="2026-11-01", target_time="00:48:00",
    )

    action = _goal_action(
        instruction="completar a meia, chegar bem",
        race_name="Meia de SP",
        distance_km=21,
        race_date="2026-10-01",  # MAIS PRÓXIMA que a 10k -> reancorar
        target_time=None,
        relationship="stepping_stone",
    )

    reply, repo, _, _ = _run(action, runner=runner, say="Foco em completar! 🎯")

    anchor = _anchor_updates(repo)
    assert anchor["race_date"] == "2026-10-01"
    assert anchor["target_time"] is None  # limpou o 00:48:00 herdado
