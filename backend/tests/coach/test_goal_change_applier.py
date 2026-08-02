import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.goal_change_applier import (
    _ASK_WHICH_GOAL,
    GoalChangeApplier,
)
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.goal_change_applier"


def _patches(pending=False):
    """Contexto comum: estado pendente controlável + repos/serviços mockados."""

    pending_repo = MagicMock()
    pending_repo.is_pending.return_value = pending

    return (
        patch(f"{MODULE}.PendingGoalRepository", return_value=pending_repo),
        pending_repo,
    )


def test_not_a_goal_change_returns_none_without_calling_ia():

    runner = make_runner()

    pending_patch, pending_repo = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
    ):

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "como foi meu treino de ontem?",
            )
        )

    assert reply is None
    mock_parser.parse.assert_not_called()
    pending_repo.mark.assert_not_called()


def test_false_positive_without_explicit_change_falls_through():
    """Portão barato deu falso positivo ('prova' + 'agora'), mas não é um
    pedido CLARO de trocar meta e a IA não achou objetivo -> segue o fluxo
    normal, sem perguntar nada nem armar estado."""

    runner = make_runner()

    pending_patch, pending_repo = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
    ):

        mock_parser.parse = AsyncMock(return_value={})

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "a prova que fiz agora foi ótima",
            )
        )

    assert reply is None
    mock_repo_cls.return_value.update_fields.assert_not_called()
    pending_repo.mark.assert_not_called()


def test_explicit_change_without_goal_arms_pending_and_asks():
    """'quero trocar meus objetivos' (sem dizer qual): o coach pergunta e
    ARMA o estado, pra ler a resposta seguinte como a meta nova."""

    runner = make_runner()

    pending_patch, pending_repo = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
    ):

        mock_parser.parse = AsyncMock(return_value={})

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "quero trocar meus objetivos",
            )
        )

    assert reply == _ASK_WHICH_GOAL
    pending_repo.mark.assert_called_once_with("renato")
    mock_repo_cls.return_value.update_fields.assert_not_called()


def test_pending_answer_without_goal_releases_state():
    """Estava esperando a meta, mas a resposta não trouxe uma -> solta o
    estado e deixa o fluxo normal seguir."""

    runner = make_runner()

    pending_patch, pending_repo = _patches(pending=True)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
    ):

        mock_parser.parse = AsyncMock(return_value={})

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "ah deixa pra lá, outra hora",
            )
        )

    assert reply is None
    pending_repo.clear.assert_called_once_with("renato")


def test_pending_answer_with_aspiration_registers_without_regenerating():
    """Resposta pós-pergunta ('quero correr 21km, com saúde') SEM data:
    registra a meta + memória de aspiração e MANTÉM a semana — não regera
    plano agressivo. É o bug que estamos matando."""

    runner = make_runner(external_coach=False)

    pending_patch, pending_repo = _patches(pending=True)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "correr 21km com saúde",
                "target_race": "21 km",
                "target_time": None,
                "race_date": None,
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "quero conseguir correr 21km, com saúde",
            )
        )

    # meta registrada (só o goal — sem virar a semana nem gravar prova/data)
    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {"goal": "correr 21km com saúde"},
    )

    # aspiração de longo prazo vira memória 'objetivo'
    mock_memory.process.assert_called_once()
    ops = mock_memory.process.call_args.args[1]
    assert ops["add"][0]["category"] == "objetivo"
    assert "correr 21km com saúde" in ops["add"][0]["content"]

    # NÃO regenerou a semana
    mock_provider.for_profile.assert_not_awaited()

    # estado consumido + mensagem tranquiliza (mantém a semana)
    pending_repo.clear.assert_called_once_with("renato")
    assert "correr 21km com saúde" in reply
    assert "semana atual segue" in reply


def test_concrete_goal_with_target_time_regenerates_and_confirms():
    """Meta com tempo-alvo (concreta): atualiza o perfil e regera a semana."""

    runner = make_runner(external_coach=False)

    pending_patch, _ = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "meia maratona sub-2h",
                "target_race": "21 km",
                "target_time": "02:00:00",
                "race_date": None,
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        plan = MagicMock()

        mock_provider.for_profile = AsyncMock(
            return_value=(runner, plan),
        )

        mock_formatter.week_plan_message.return_value = "[PLANO]"

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "quero mudar minha meta pra meia sub-2h",
            )
        )

    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {
            "goal": "meia maratona sub-2h",
            "target_race": "21 km",
            "target_time": "02:00:00",
        },
    )

    mock_provider.for_profile.assert_awaited_once_with("renato", force=True)

    assert "meia maratona sub-2h" in reply
    assert "[PLANO]" in reply


def test_aspiration_one_shot_updates_goal_only():
    """'quero mudar meu objetivo pra só saúde' (uma tacada, sem data/tempo)
    não deve apagar a prova já registrada — cai no caminho de aspiração."""

    runner = make_runner(
        target_race="10 km", target_time="00:50:00", race_date="2026-09-01",
    )

    pending_patch, _ = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "só saúde e constância",
                "target_race": None,
                "target_time": None,
                "race_date": None,
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "quero mudar meu objetivo pra só saúde",
            )
        )

    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {"goal": "só saúde e constância"},
    )
    mock_memory.process.assert_called_once()
    mock_provider.for_profile.assert_not_awaited()


def test_additional_objective_accumulates_without_overwriting():
    """'além da prova, também quero emagrecer' SOMA um objetivo (não troca):
    funde no headline sem apagar o anterior, grava memória, mantém a semana e
    NÃO mexe na prova já registrada."""

    runner = make_runner(
        goal="correr 21km com saúde",
        target_race="10 km",
        race_date="2026-08-23",
        external_coach=False,
    )

    pending_patch, _ = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "emagrecer",
                "target_race": None,
                "target_time": None,
                "race_date": None,
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato",
                runner,
                "além da minha prova, também quero emagrecer",
            )
        )

    # headline FUNDE os dois (não sobrescreve); só o goal muda (prova intacta)
    mock_repo.update_fields.assert_called_once_with(
        "renato",
        {"goal": "correr 21km com saúde; e também emagrecer"},
    )

    ops = mock_memory.process.call_args.args[1]
    assert ops["add"][0]["category"] == "objetivo"
    assert "emagrecer" in ops["add"][0]["content"]

    # não regenera a semana (objetivo sem data)
    mock_provider.for_profile.assert_not_awaited()
    assert "Somei" in reply


def test_additional_nearer_dated_race_becomes_anchor_and_regenerates():
    """Objetivo adicional COM prova mais próxima que a atual vira a âncora de
    periodização e regera a semana."""

    runner = make_runner(
        goal="maratona no fim do ano",
        race_date="2026-11-15",
        external_coach=False,
    )

    pending_patch, _ = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.RunnerMemoryService"),
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
        patch(f"{MODULE}.WeeklyPlanMessageFormatter") as mock_formatter,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "10k em agosto",
                "target_race": "10 km",
                "target_time": None,
                "race_date": "2026-08-23",
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock(return_value=(runner, MagicMock()))
        mock_formatter.week_plan_message.return_value = "[PLANO]"

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato",
                runner,
                "além da minha prova de fim de ano, também quero um 10k em 23/08",
            )
        )

    updates = mock_repo.update_fields.call_args.args[1]
    assert updates["race_date"] == "2026-08-23"   # a mais próxima ancora
    mock_provider.for_profile.assert_awaited_once_with("renato", force=True)
    assert "[PLANO]" in reply


def test_additional_farther_dated_race_stays_in_memory():
    """Objetivo adicional com prova MAIS DISTANTE que a atual não muda a âncora
    (nem regera) — fica guardado como meta futura."""

    runner = make_runner(
        goal="10k em agosto",
        race_date="2026-08-23",
        external_coach=False,
    )

    pending_patch, _ = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.RunnerMemoryService"),
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "maratona no fim do ano",
                "target_race": "42 km",
                "target_time": None,
                "race_date": "2026-11-15",
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        asyncio.run(
            GoalChangeApplier.handle(
                "renato",
                runner,
                "além da minha prova de 10k, também quero uma maratona no fim do ano",
            )
        )

    updates = mock_repo.update_fields.call_args.args[1]
    assert "race_date" not in updates          # âncora atual (mais próxima) fica
    mock_provider.for_profile.assert_not_awaited()


def test_external_coach_concrete_goal_records_without_regenerating():
    """Treinador humano + meta concreta: só registra, nunca regera o plano."""

    runner = make_runner(external_coach=True)

    pending_patch, _ = _patches(pending=False)

    with (
        pending_patch,
        patch(f"{MODULE}.OnboardingAnswerParser") as mock_parser,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_repo_cls,
        patch(f"{MODULE}.CurrentPlanProvider") as mock_provider,
    ):

        mock_parser.parse = AsyncMock(
            return_value={
                "goal": "meia sub-2h",
                "target_race": "21 km",
                "target_time": "02:00:00",
                "race_date": None,
            }
        )

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_provider.for_profile = AsyncMock()

        reply = asyncio.run(
            GoalChangeApplier.handle(
                "renato", runner, "quero mudar minha meta pra meia sub-2h",
            )
        )

    mock_repo.update_fields.assert_called_once()
    mock_provider.for_profile.assert_not_awaited()
    assert "meia sub-2h" in reply
