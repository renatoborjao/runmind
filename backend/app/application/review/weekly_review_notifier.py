from app.application.coach.intelligence.state_portrait_service import (
    StatePortraitService,
)
from app.application.coach.memory.coach_learning_engine import (
    CoachLearningEngine,
)
from app.application.coach.memory.coach_learning_service import (
    CoachLearningService,
)
from app.application.coach.memory.coaching_signal_recorder import (
    CoachingSignalRecorder,
)
from app.application.coach.memory.week_evidence_builder import (
    WeekEvidenceBuilder,
)
from app.application.coach.writer.help_menu import HelpMenu
from app.application.coach.writer.state_portrait_writer import (
    StatePortraitWriter,
)
from app.application.notifications.coach_outbox import (
    CoachOutbox,
)
from app.application.review.weekly_review_builder import (
    WeeklyReviewBuilder,
)
from app.application.review.weekly_review_message_formatter import (
    WeeklyReviewMessageFormatter,
)
from app.application.review.weekly_review_narrative_writer import (
    WeeklyReviewNarrativeWriter,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import now_in, use_athlete_timezone
from app.infrastructure.persistence.coach_learning_repository import (
    CoachLearningRepository,
)
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# cobre as 8 semanas da tendência com folga
HISTORY_LIMIT = 60

# domingo (weekday 6) 19h LOCAL: fecha a semana ISO (o dia já rendeu) e o
# cérebro APRENDE com ela — uma hora ANTES da entrega do plano (20h), pra a
# semana nova sair já moldada pelo aprendizado fresco. Ver [[project_memoria_treinamento]].
_SUNDAY = 6

REVIEW_HOUR = 19


def _week_key(local) -> str:

    iso = local.isocalendar()

    return f"{iso[0]}-W{iso[1]:02d}"


class WeeklyReviewNotifier:

    @staticmethod
    async def notify_all() -> None:
        """Roda de HORA EM HORA; cada _notify_one decide se é o horário local
        do atleta (domingo 19h) e faz dedup."""

        for profile in RunnerProfileRepository().list_all():

            try:

                await WeeklyReviewNotifier._notify_one(profile)

            except Exception as e:

                print(
                    f"Falha ao enviar resumo semanal para "
                    f"'{profile}': {e}",
                )

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        # só no domingo 19h LOCAL do atleta, uma vez por semana (dedup)
        if local.weekday() != _SUNDAY or local.hour != REVIEW_HOUR:

            return

        period = _week_key(local)

        if DispatchGuard.already_sent("weekly_review", profile, period):

            return

        DispatchGuard.mark("weekly_review", profile, period)

        history = await LoadTrainingHistory.execute(
            profile=profile,
            limit=HISTORY_LIMIT,
        )

        review = WeeklyReviewBuilder.build(
            runner,
            history,
        )

        # a IA escreve a "leitura da semana" guiada pelo objetivo do atleta;
        # se falhar, o formatter usa o fallback determinístico
        narrative = await WeeklyReviewNarrativeWriter.write(
            runner.name,
            review,
        )

        message = WeeklyReviewMessageFormatter.format(
            runner.name,
            review,
            narrative,
        )

        if message is None:

            return

        # rodapé "💡 Você sabia?" rotativo — descoberta gradual do que dá pra
        # perguntar ao bot, uma dica por semana (rotaciona pelo nº da semana)
        message = (
            f"{message}\n\n{HelpMenu.weekly_tip(local.isocalendar()[1])}"
        )

        await CoachOutbox.send(
            runner,
            message,
        )

        # logo depois, o RETRATO ÚNICO "como você está" (corpo & carga + forma
        # cruzados) — mensagem separada pra não misturar o tom. O gate semanal
        # acima já cobre o dedup.
        await WeeklyReviewNotifier._send_state_portrait(profile, runner)

        # atualiza a ÂNCORA CONTÍNUA do VDOT (best_efforts do Strava das corridas
        # novas) ANTES de checar o progresso de pace — pra o floor estar fresco.
        await WeeklyReviewNotifier._refresh_best_efforts(profile)

        # ficou mais rápido? se a forma subiu de forma sustentada, o VDOT (fonte
        # dos paces) subiu — avisa o atleta e mostra os ritmos novos (fecha o
        # loop da evolução). Best-effort, uma vez por marco.
        await WeeklyReviewNotifier._notify_pace_progress(
            profile, runner, history,
        )

        # loop de CADÊNCIA: acompanha a evolução da forma e reage (dica inicial,
        # progresso, alvo batido ou um re-cutução se travar). Best-effort.
        await WeeklyReviewNotifier._notify_cadence_progress(
            profile, runner, history,
        )

        # e, silenciosamente, o cérebro coach APRENDE com a semana que fechou
        # (nada é enviado ao atleta — modo observação; ver [[project]]).
        await WeeklyReviewNotifier._distill_learnings(
            profile, runner, history,
        )

    @staticmethod
    async def _refresh_best_efforts(profile) -> None:
        """Sobe a marca-d'água do VDOT contínuo (best_efforts do Strava) das
        corridas novas. Best-effort: falhar aqui nunca derruba o resumo."""

        try:

            from app.application.history.best_effort_refresh import (
                BestEffortRefresh,
            )

            await BestEffortRefresh.refresh(profile)

        except Exception as e:

            print(f"Falha no refresh de best-effort de '{profile}': {e}")

    @staticmethod
    async def _notify_pace_progress(profile, runner, history) -> None:
        """Aviso de "você ficou mais rápido" + ritmos novos, quando a forma
        subiu além do último marco. Best-effort: falhar aqui nunca derruba o
        resumo (que já foi enviado)."""

        try:

            from app.application.coach.intelligence.pace_progress_notifier import (
                PaceProgressNotifier,
            )

            message = PaceProgressNotifier.check(profile, runner, history)

            if message:

                await CoachOutbox.send(runner, message)

        except Exception as e:

            print(f"Falha no aviso de pace de '{profile}': {e}")

    @staticmethod
    async def _notify_cadence_progress(profile, runner, history) -> None:
        """Loop de cadência: dica inicial / progresso / alvo batido / um
        re-cutução se travar. Best-effort: falhar aqui nunca derruba o resumo
        (que já foi enviado)."""

        try:

            from app.application.coach.intelligence.cadence_progress_notifier import (  # noqa: E501
                CadenceProgressNotifier,
            )

            message = CadenceProgressNotifier.check(profile, runner, history)

            if message:

                await CoachOutbox.send(runner, message)

        except Exception as e:

            print(f"Falha no loop de cadência de '{profile}': {e}")

    @staticmethod
    async def _distill_learnings(profile, runner, history) -> None:
        """Destila a evidência da semana (prescrito×executado + correções
        aceitas + resposta do corpo) em aprendizados duráveis sobre o atleta.
        Best-effort e SILENCIOSO: falhar aqui nunca afeta o que o atleta
        recebe (o resumo já foi enviado). Não injeta nada no plano — isso é
        decisão de flag, à parte."""

        try:

            evidence = WeekEvidenceBuilder.build(profile, history)

            if not evidence:

                return

            current = CoachLearningRepository().active(profile)

            ops = await CoachLearningEngine.extract(
                runner.name,
                current,
                evidence,
            )

            CoachLearningService.process(
                profile,
                ops,
                goal_kind="race" if runner.race_date else "health",
            )

            # os sinais crus da Fonte A já viraram aprendizado — zera pra
            # próxima semana não recontar
            CoachingSignalRecorder.clear(profile)

        except Exception as e:

            print(f"Falha ao destilar aprendizados de '{profile}': {e}")

    @staticmethod
    async def _send_state_portrait(profile: str, runner) -> None:
        """Retrato único "como você está" pós-resumo (corpo & carga + forma
        cruzados). Best-effort: falhar aqui nunca derruba o resumo (que já foi
        enviado). O serviço grava o snapshot canônico de domingo do corpo.
        None quando nenhum eixo tem lastro (atleta novíssimo) → não envia."""

        try:

            reading, evolution = StatePortraitService.read(profile)

            message = StatePortraitWriter.write(
                reading, evolution, runner.name
            )

            if message is None:

                return

            await CoachOutbox.send(runner, message)

        except Exception as e:

            print(f"Falha no retrato de '{profile}': {e}")
