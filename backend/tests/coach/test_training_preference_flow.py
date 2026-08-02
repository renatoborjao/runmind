import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.training_preference_flow import (
    TrainingPreferenceFlow,
)
from app.application.coach.planning.training_preference_engine import (
    TrainingPreference,
)
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.training_preference_flow"


def test_gate_catches_durable_shape_requests():
    """Preferência de FORMA da rotina COM sinal de durabilidade (pra frente)
    entra; ajuste só desta semana e pergunta NÃO entram (seguem outros fluxos)."""

    yes = [
        "queria manter os treinos de semana em ate 50 minutos, dia de "
        "semana e sempre corrido",
        "a partir da proxima semana quero terca e quinta mais curtas",
        "fim de semana sem pressa, mas durante a semana pouco tempo",
    ]
    no = [
        "deixa a semana mais leve",          # ajuste desta semana (sem horizonte)
        "como foi meu ultimo treino?",       # pergunta
        "bom dia coach",                     # cumprimento
    ]

    for t in yes:
        assert TrainingPreferenceFlow._looks_like(t) is True, t
    for t in no:
        assert TrainingPreferenceFlow._looks_like(t) is False, t


def _run(text, runner=None, preference="unset"):

    runner = runner or make_runner()

    with (
        patch(f"{MODULE}.RunnerMemoryRepository") as mem_repo_cls,
        patch(f"{MODULE}.ConversationRepository") as conv_repo_cls,
        patch(f"{MODULE}.TrainingPreferenceEngine") as engine,
        patch(f"{MODULE}.RunnerMemoryService") as memory_service,
        patch(f"{MODULE}.PlanProposalRepository") as proposal_cls,
    ):

        mem_repo_cls.return_value.active.return_value = []
        conv_repo_cls.return_value.recent_turns.return_value = []

        if preference != "unset":
            engine.extract = AsyncMock(return_value=preference)

        reply = asyncio.run(
            TrainingPreferenceFlow.handle("renato", runner, text)
        )

        return reply, engine, memory_service, proposal_cls


def test_gate_miss_never_calls_engine():

    reply, engine, memory_service, _ = _run("bom dia coach")

    assert reply is None
    engine.extract.assert_not_called()
    memory_service.process.assert_not_called()


def test_engine_declines_falls_through_without_writing():
    """IA diz que não é durável (é ajuste desta semana / desabafo): devolve
    None pro turno seguir, e NÃO grava memória."""

    reply, _, memory_service, proposal_cls = _run(
        "a partir de semana que vem quero treino",  # passa no portão
        preference=None,                             # engine recusa
    )

    assert reply is None
    memory_service.process.assert_not_called()
    proposal_cls.return_value.clear.assert_not_called()


def test_durable_preference_is_saved_and_confirmed():
    """O caso do Renato: entende, grava na memória (categoria preferencia),
    limpa proposta órfã e confirma — sem tocar na semana atual."""

    preference = TrainingPreference(
        category="preferencia",
        content=(
            "Prefere treinos de dia de semana em até ~50 min (ter/qui); "
            "fim de semana sem limite; a partir de 04/08"
        ),
        reply=(
            "Anotado! A partir da próxima semana teus treinos de terça e "
            "quinta ficam em até ~50 min, fim de semana sem pressa. Vou "
            "montar teus próximos planos assim. 💪"
        ),
        archive=[],
    )

    reply, _, memory_service, proposal_cls = _run(
        "queria manter os treinos de semana em ate 50 min, a partir "
        "da proxima",
        preference=preference,
    )

    assert reply == preference.reply

    # gravou no trilho da memória evolutiva, como "add" de preferencia
    memory_service.process.assert_called_once()
    ops = memory_service.process.call_args.args[1]
    assert ops["add"] == [
        {"category": "preferencia", "content": preference.content}
    ]

    # proposta órfã desta semana é descartada (o atleta redirecionou o rumo)
    proposal_cls.return_value.clear.assert_called_once_with("renato")


def test_archive_ids_flow_through_to_memory():
    """Preferência que SUBSTITUI outra (novo orçamento de tempo) arquiva a
    antiga junto — não acumula contradição."""

    preference = TrainingPreference(
        category="preferencia",
        content="Prefere treinos de semana em até 40 min a partir de 04/08",
        reply="Beleza, ajustei pra 40 min. 💪",
        archive=["m-1234abcd"],
    )

    _, _, memory_service, _ = _run(
        "na verdade, a partir de agora mantem os treinos de semana em 40 min",
        preference=preference,
    )

    ops = memory_service.process.call_args.args[1]
    assert ops["archive"] == ["m-1234abcd"]


def test_onboarding_pillars_are_passed_to_engine():
    """A preferência é COMPLEMENTAR: o motor recebe os dias FIXOS do onboarding
    (em pt-BR) e a meta, pra não redefinir dias nem furar o objetivo."""

    runner = make_runner(
        goal="correr 21 km bem, sem data definida",
        preferred_running_days=["Tuesday", "Thursday", "Saturday"],
        target_race="10 km",
        race_date="2026-08-23",
    )

    _, engine, _, _ = _run(
        "queria manter os treinos de semana em ate 50 min, a partir da proxima",
        runner=runner,
        preference=None,
    )

    kwargs = engine.extract.call_args.kwargs
    assert kwargs["training_days"] == "terça-feira, quinta-feira, sábado"
    # aspiração de fundo (21k) + prova concreta com a DATA (23/08) — o motor
    # precisa saber que há prova perto pra proteger o essencial
    assert "correr 21 km" in kwargs["objective"]
    assert "10 km" in kwargs["objective"]
    assert "23/08/2026" in kwargs["objective"]


def test_external_coach_still_saves_but_engine_told_no_plan():
    """Atleta de treinador humano: ainda grava a preferência (memória é
    dinâmica), mas avisa o engine que NÃO montamos plano (plan_owned=False),
    pra a confirmação não prometer plano."""

    preference = TrainingPreference(
        category="preferencia",
        content="Prefere treinos de semana curtos",
        reply="Anotado! 💪",
        archive=[],
    )

    _, engine, memory_service, _ = _run(
        "durante a semana sempre pouco tempo, mantem os treinos curtos",
        runner=make_runner(external_coach=True),
        preference=preference,
    )

    assert engine.extract.call_args.kwargs["plan_owned"] is False
    memory_service.process.assert_called_once()
