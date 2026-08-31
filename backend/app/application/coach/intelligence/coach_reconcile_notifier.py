"""As conversas de RECONCILIAÇÃO do coach: quando há uma lacuna entre o que o
atleta REGISTROU e o que ele VIVE, o coach pergunta (uma vez, sem nag):

  1) FREQUÊNCIA — treina em ROTINA além dos dias registrados -> "quer oficializar
     mais um dia?" (o plano já não subestima o volume; aqui é sobre a frequência,
     que é escolha DELE);
  2) META VAGA — sem prova/distância/prazo -> "é saúde ou uma prova? me diz o
     alvo que eu periodizo".

Atrás da flag `coach_reconcile_enabled` (default OFF) + canário. Uma por atleta
por dia (dedup), governada (kind não-essencial passa pelo teto), orientar-não-
repetir (pergunta só quando o padrão é novo). Ver [[project_reconciliacao_coach]],
[[feedback_orientar_nao_mandar]] e [[project_governador_proativos]]."""

from datetime import time

from app.application.coach.intelligence.goal_clarity_checker import (
    GoalClarityChecker,
    goal_clarity_message,
)
from app.application.history.training_reality_analyzer import (
    TrainingRealityAnalyzer,
    frequency_reconcile_message,
)
from app.application.notifications.coach_outbox import CoachOutbox
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import LoadTrainingHistory
from app.core.clock import now_in, use_athlete_timezone
from app.core.config import get_settings
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# janela de horário local pra soltar a pergunta (nada de madrugada)
WINDOW_START = time(9, 0)
WINDOW_END = time(20, 0)

_KIND = "reconcile"


class CoachReconcileNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await CoachReconcileNotifier._notify_one(profile)

            except Exception as e:

                print(f"Reconciliação do coach falhou p/ '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        # flag + canário: DESLIGADA por padrão (nada sai)
        if not get_settings().coach_reconcile_active_for(profile):

            return

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        if not (WINDOW_START <= local.time() <= WINDOW_END):

            return

        # no máximo UMA reconciliação por atleta por dia (não empilha)
        day = local.date().isoformat()

        if DispatchGuard.already_sent("reconcile_day", profile, day):

            return

        # a frequência vem primeiro (é sobre o plano; mais acionável)
        message = await CoachReconcileNotifier._frequency_ask(profile, runner)

        if not message:

            message = await CoachReconcileNotifier._goal_ask(profile, runner)

        if not message:

            return

        await CoachOutbox.send(runner, message, profile=profile, kind=_KIND)

        DispatchGuard.mark("reconcile_day", profile, day)

    @staticmethod
    async def _frequency_ask(profile: str, runner) -> str | None:
        """Pergunta de oficializar o dia extra — só quando é ROTINA e ainda não
        foi perguntada pra esta configuração de dias (dedup por nº de dias)."""

        history = await LoadTrainingHistory.execute(profile=profile)

        reg = len(runner.preferred_running_days)

        verdict = TrainingRealityAnalyzer.assess(reg, history.activities)

        message = frequency_reconcile_message(runner.name, verdict)

        if not message:

            return None

        # dedup por nº de dias registrados: se ele mudar os dias, re-elegível
        key = f"{reg}->{round(verdict.real_runs_per_week)}"

        if DispatchGuard.already_sent("reconcile_freq", profile, key):

            return None

        DispatchGuard.mark("reconcile_freq", profile, key)

        return message

    @staticmethod
    async def _goal_ask(profile: str, runner) -> str | None:
        """Pergunta pra cravar a meta vaga — uma vez por 'assinatura' de meta
        (se a meta mudar, re-elegível)."""

        goal = BuildTrainingGoal.execute(runner)

        objectives = CoachReconcileNotifier._memory_objectives(profile)

        clarity = GoalClarityChecker.assess(runner, goal, objectives)

        message = goal_clarity_message(runner.name, clarity)

        if not message:

            return None

        key = (runner.goal or "") + "|" + (clarity.latent_distance_hint or "")

        if DispatchGuard.already_sent("reconcile_goal", profile, key):

            return None

        DispatchGuard.mark("reconcile_goal", profile, key)

        return message

    @staticmethod
    def _memory_objectives(profile: str) -> list[str]:
        """Os textos de memória do tipo 'objetivo' (pra a pergunta citar a prova
        que ele já mencionou). Best-effort."""

        try:

            from app.infrastructure.persistence.runner_memory_repository import (
                RunnerMemoryRepository,
            )

            entries = RunnerMemoryRepository().load(profile)

            return [
                e.content
                for e in entries
                if getattr(e, "status", "active") == "active"
                and getattr(e, "category", "") == "objetivo"
            ]

        except Exception:

            return []
