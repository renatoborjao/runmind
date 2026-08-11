"""Validação OFFLINE do executor do cérebro do coach — o cérebro é MOCKADO
(decisão fixa) e a gente verifica que cada decisão aciona a 'mão' certa. Cobre
os casos reais que quebraram ao vivo (mover com escopo, aplicar, refinar,
cartão exato, conversa). Ver [[project_roteador_acao_ia]]."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.coach_brain import (
    BrainAction,
    BrainDecision,
)
from app.application.coach.conversation.coach_brain_executor import (
    CoachBrainExecutor,
)
from app.application.coach.planning.move_skip_engine import MoveSkipRequest
from app.domain.entities.plan_proposal import PlanProposal
from tests.coach.factories import make_runner

M = "app.application.coach.conversation.coach_brain_executor"


def _pending() -> PlanProposal:
    return PlanProposal(
        kind="negotiation",
        week_start="2026-08-04",
        preview="Proposta anterior. Posso aplicar?",
        created_at="2026-08-08T20:00:00",
        operations=[{"action": "drop", "day": "Tuesday"}],
    )


def _plan() -> MagicMock:
    plan = MagicMock()
    plan.sessions = [MagicMock()]
    plan.source = "ritmind"
    plan.week_start = date(2026, 8, 4)
    return plan


def _plan_patch():
    return patch(
        f"{M}.CurrentPlanProvider.for_profile",
        new=AsyncMock(return_value=(make_runner(), _plan())),
    )


def _run(decision, pending=None, extra_patches=()):
    """Roda o executor com contexto/repo/cérebro mockados. Devolve (reply, repo)."""

    repo = MagicMock()
    repo.load.return_value = pending

    ctx = [
        patch(f"{M}.ConversationContextBuilder.build", new=AsyncMock(return_value="FATOS")),
        patch(f"{M}.PlanProposalRepository", return_value=repo),
        patch(f"{M}.CoachBrain.decide", new=AsyncMock(return_value=decision)),
        *extra_patches,
    ]

    for c in ctx:
        c.start()

    try:
        reply = asyncio.run(
            CoachBrainExecutor.handle("renato", make_runner(), "mensagem")
        )
    finally:
        for c in reversed(ctx):
            c.stop()

    return reply, repo


def test_none_decision_falls_back():
    """Cérebro indeciso/fora do ar => None (cai na cascata determinística)."""

    reply, _ = _run(None)

    assert reply is None


def test_chat_only_returns_coach_voice():

    reply, repo = _run(BrainDecision(say="Bora, tá voando! 👊"))

    assert reply == "Bora, tá voando! 👊"
    repo.save.assert_not_called()


def test_answer_card_renders_exact_and_frames_with_voice():

    decision = BrainDecision(say="Teu plano 👇", answer_card="weekly_plan")

    reply, _ = _run(
        decision,
        extra_patches=[
            patch(f"{M}.OnDemandAnswers.answer", new=AsyncMock(return_value="PLANO EXATO")),
        ],
    )

    assert reply == "Teu plano 👇\n\nPLANO EXATO"


def test_move_action_builds_scoped_proposal_and_saves_pending():

    decision = BrainDecision(
        say="Movo teu longão pra amanhã — posso aplicar?",
        action=BrainAction("move", "single_session", "Saturday", "mover pra amanhã"),
    )

    request = MoveSkipRequest(
        action="move", day="Sunday", target_day="Saturday",
        message="Movo teu longão de domingo pra sábado. Posso aplicar?",
    )

    reply, repo = _run(
        decision,
        extra_patches=[
            _plan_patch(),
            patch(f"{M}.MoveSkipEngine.propose", new=AsyncMock(return_value=request)),
            patch(
                f"{M}.MoveSkipFlow._operations",
                return_value=[{"action": "drop", "day": "Sunday"}],
            ),
        ],
    )

    assert reply == request.message
    repo.save.assert_called_once()
    saved = repo.save.call_args.args[1]
    assert saved.kind == "move"
    assert saved.operations  # candidato calculado e guardado pro "sim"


def test_apply_pending_applies_and_offers_watch():

    decision = BrainDecision(say="", on_pending="apply")

    reply, repo = _run(
        decision,
        pending=_pending(),
        extra_patches=[
            patch(f"{M}.PlanChangeApplier.apply", return_value=_plan()),
            patch(f"{M}.watch_update_offer", return_value="\n\n⌚ Quer no relógio?"),
        ],
    )

    assert "Ajustei" in reply
    assert "relógio" in reply
    repo.clear.assert_called_once_with("renato")


def test_apply_pending_uses_coach_voice_when_present():
    """O 'sim' sai na voz do coach (decision.say), não num fixo robótico."""

    decision = BrainDecision(say="Fechou, tá ajustado! 🔥", on_pending="apply")

    reply, _ = _run(
        decision,
        pending=_pending(),
        extra_patches=[
            patch(f"{M}.PlanChangeApplier.apply", return_value=_plan()),
            patch(f"{M}.watch_update_offer", return_value="\n\n⌚ Quer no relógio?"),
        ],
    )

    assert reply.startswith("Fechou, tá ajustado! 🔥")
    assert "relógio" in reply


def test_routine_preference_persists_to_memory():
    """Pedido durável de rotina => o cérebro roteia pro motor de preferência,
    que grava na memória evolutiva. Antes isso era engolido como conversa."""

    decision = BrainDecision(
        say="Fechado, monto os próximos assim! 👍",
        action=BrainAction("routine", "week", None, "treinos de semana até 50 min"),
    )

    reply, repo = _run(
        decision,
        extra_patches=[
            patch(
                "app.application.coach.conversation.training_preference_flow."
                "TrainingPreferenceFlow.apply_preference",
                new=AsyncMock(return_value="Anotado: dias de semana até ~50 min. 👍"),
            ),
        ],
    )

    assert reply == "Anotado: dias de semana até ~50 min. 👍"
    repo.save.assert_not_called()  # rotina vira memória, não proposta pendente


def test_one_off_routes_to_flow():
    """'monta um treino pra domingo' => cérebro roteia pro fluxo do avulso
    (dia que o plano não cobre). Antes o cérebro não tinha essa mão."""

    decision = BrainDecision(
        say="Bora, monto teu treino de domingo! 🏃",
        action=BrainAction("one_off", "single_session", "Sunday", "treino pra domingo"),
    )

    reply, repo = _run(
        decision,
        extra_patches=[
            patch(
                "app.application.coach.conversation.one_off_workout_flow."
                "OneOffWorkoutFlow.build_for",
                new=AsyncMock(return_value="Montei teu treino de domingo 👇 ..."),
            ),
        ],
    )

    assert reply == "Montei teu treino de domingo 👇 ..."
    repo.save.assert_not_called()  # o fluxo do avulso grava por conta própria


def test_negotiation_receives_full_athlete_context():
    """O princípio: o ajuste NUNCA é no vácuo — o NegotiationEngine recebe a
    base completa do atleta (o mesmo context_facts que o cérebro viu)."""

    decision = BrainDecision(
        say="Deixo mais leve, posso aplicar?",
        action=BrainAction("adjust", "week", None, "deixa a semana mais leve"),
    )

    negotiation = MagicMock()
    negotiation.operations = [{"action": "replace", "day": "Tuesday", "session": {}}]
    negotiation.message = "Aliviei a semana."

    propose = AsyncMock(return_value=negotiation)

    _run(
        decision,
        extra_patches=[
            _plan_patch(),
            patch(f"{M}.NegotiationEngine.propose", new=propose),
            patch(f"{M}.PlanChangeApplier._apply_operations"),
            patch(
                f"{M}.WeeklyPlanMessageFormatter.session_lines",
                return_value=["terça — leve"],
            ),
        ],
    )

    # o context builder mockado devolve "FATOS" — tem que chegar no engine
    assert propose.call_args.kwargs.get("athlete_context") == "FATOS"


def test_compound_move_and_adjust_builds_single_proposal():
    """'passa o longão pra sábado e deixa livre' = UMA proposta: move + ajuste
    do conteúdo da sessão movida (a ressalva do composto, fechada)."""

    decision = BrainDecision(
        say="Movo pra sábado e deixo livre — posso aplicar?",
        action=BrainAction(
            "move", "single_session", "Saturday", "passa pra sábado",
            content_change="livre, sem pace, só somar km",
        ),
    )

    request = MoveSkipRequest(
        action="move", day="Sunday", target_day="Saturday",
        message="Movo teu longão de domingo pra sábado. Posso aplicar?",
    )

    negotiation = MagicMock()
    negotiation.operations = [{"action": "replace", "day": "Saturday", "session": {}}]
    negotiation.message = "Deixei o de sábado livre, sem pace."

    reply, repo = _run(
        decision,
        extra_patches=[
            _plan_patch(),
            patch(f"{M}.MoveSkipEngine.propose", new=AsyncMock(return_value=request)),
            patch(
                f"{M}.MoveSkipFlow._operations",
                return_value=[
                    {"action": "drop", "day": "Sunday"},
                    {"action": "replace", "day": "Saturday", "session": {}},
                ],
            ),
            patch(f"{M}.NegotiationEngine.propose", new=AsyncMock(return_value=negotiation)),
            patch(f"{M}.PlanChangeApplier._apply_operations"),
            patch(
                f"{M}.WeeklyPlanMessageFormatter.session_lines",
                return_value=["sábado — Longão livre"],
            ),
        ],
    )

    repo.save.assert_called_once()
    saved = repo.save.call_args.args[1]
    # operações combinadas: move (drop origem + replace destino) + ajuste do destino
    assert {"action": "drop", "day": "Sunday"} in saved.operations
    assert saved.operations[-1] == negotiation.operations[0]
    assert "Como fica" in reply


def test_two_moves_in_one_message_build_single_combined_proposal():
    """O bug do Renato: 'troca terça pra quarta E quinta pra sexta' — DUAS
    trocas numa mensagem viram UMA proposta com as operações das DUAS (nenhuma
    fica de fora). Cada move é calculado sobre o plano já com o anterior."""

    decision = BrainDecision(
        say="Movo terça pra quarta e quinta pra sexta — posso aplicar?",
        actions=[
            BrainAction("move", "single_session", "Wednesday", "terça pra quarta"),
            BrainAction("move", "single_session", "Friday", "quinta pra sexta"),
        ],
    )

    req1 = MoveSkipRequest(
        action="move", day="Tuesday", target_day="Wednesday",
        message="Movo teu treino de terça pra quarta.",
    )
    req2 = MoveSkipRequest(
        action="move", day="Thursday", target_day="Friday",
        message="Movo teu treino de quinta pra sexta.",
    )

    ops1 = [
        {"action": "drop", "day": "Tuesday"},
        {"action": "replace", "day": "Wednesday", "session": {}},
    ]
    ops2 = [
        {"action": "drop", "day": "Thursday"},
        {"action": "replace", "day": "Friday", "session": {}},
    ]

    reply, repo = _run(
        decision,
        extra_patches=[
            _plan_patch(),
            patch(
                f"{M}.MoveSkipEngine.propose",
                new=AsyncMock(side_effect=[req1, req2]),
            ),
            patch(f"{M}.MoveSkipFlow._operations", side_effect=[ops1, ops2]),
            patch(f"{M}.PlanChangeApplier._apply_operations"),
            patch(
                f"{M}.WeeklyPlanMessageFormatter.session_lines",
                return_value=["quarta — Intervalado", "sexta — Rodagem"],
            ),
        ],
    )

    repo.save.assert_called_once()
    saved = repo.save.call_args.args[1]

    # as operações das DUAS trocas estão na proposta (nenhuma ficou de fora)
    assert {"action": "drop", "day": "Tuesday"} in saved.operations
    assert {"action": "drop", "day": "Thursday"} in saved.operations
    assert saved.operations == ops1 + ops2
    assert "Como fica" in reply


def test_reject_pending_clears_without_applying():

    decision = BrainDecision(say="Tranquilo, deixo como está. 👍", on_pending="reject")

    reply, repo = _run(decision, pending=_pending())

    assert "deixo como está" in reply
    repo.clear.assert_called_once_with("renato")


def test_refine_discards_old_and_reproposes_scoped():
    """Bug do Renato: correção de escopo não descarta — re-propõe só a sessão
    apontada. Cérebro devolve on_pending=refine + ação corrigida."""

    decision = BrainDecision(
        say="Ah, só o de amanhã então!",
        on_pending="refine",
        action=BrainAction("simplify", "single_session", "Saturday", "ritmo livre, sem pace"),
    )

    negotiation = MagicMock()
    negotiation.operations = [{"action": "replace", "day": "Saturday", "session": {}}]
    negotiation.message = "Deixei só o de amanhã livre."

    reply, repo = _run(
        decision,
        pending=_pending(),
        extra_patches=[
            _plan_patch(),
            patch(
                f"{M}.NegotiationEngine.propose",
                new=AsyncMock(return_value=negotiation),
            ),
            patch(f"{M}.PlanChangeApplier._apply_operations"),
            patch(
                f"{M}.WeeklyPlanMessageFormatter.session_lines",
                return_value=["sábado — Longão livre"],
            ),
        ],
    )

    # a proposta velha foi descartada e uma NOVA foi montada + guardada
    repo.clear.assert_called_once_with("renato")
    repo.save.assert_called_once()
    saved = repo.save.call_args.args[1]
    assert saved.operations == negotiation.operations
    assert "Deixei só o de amanhã" in reply
