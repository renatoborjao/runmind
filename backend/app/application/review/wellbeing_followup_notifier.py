"""Loop de acompanhamento: quando o atleta relatou DOENÇA ou DOR há alguns
dias, o coach VOLTA pra perguntar como está ("melhorou da gripe?", "e aquela
dor no joelho?") — o gesto de um treinador que LEMBRA. UM toque por episódio.

Não muda plano nem diagnostica: acolhe e convida a responder (a resposta cai no
cérebro do coach, que já vê o check-in no contexto). Roda de hora em hora; cada
_notify_one decide se é o horário local e faz dedup. Fecha o loop da captura de
gripe/dor ([[project_analise_corpo_garmin]], item 4 de [[project_ideias_produto]])."""

from app.application.notifications.coach_outbox import CoachOutbox
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import now_in, today_local, use_athlete_timezone
from app.infrastructure.persistence.checkin_repository import CheckinRepository
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# meio-dia local: dá tempo do dia começar, sem colidir com o briefing (manhã)
# nem com o re-engajamento (17h)
FOLLOWUP_HOUR = 12

# espera antes de acompanhar (dia 0-1 já é coberto pelo aviso de descanso da
# prontidão; voltar cedo demais seria repetitivo) e janela máxima (depois disso
# a queixa é velha — o atleta já seguiu a vida)
_DELAY_DAYS = 2
_WINDOW_DAYS = 6


class WellbeingFollowUpNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await WellbeingFollowUpNotifier._notify_one(profile)

            except Exception as e:

                print(f"Falha no acompanhamento de '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        if local.hour != FOLLOWUP_HOUR:

            return

        today = today_local()

        concern = CheckinRepository().recent_concern(
            profile, today.isoformat(), _WINDOW_DAYS
        )

        if concern is None:

            return

        # cedo demais? o dia 0-1 já teve o toque de descanso — deixa respirar
        try:

            from datetime import date

            days_since = (today - date.fromisoformat(concern.day)).days

        except ValueError:

            return

        if days_since < _DELAY_DAYS:

            return

        # UM toque por episódio (a chave é o dia do relato)
        if DispatchGuard.already_sent("wellbeing_followup", profile, concern.day):

            return

        DispatchGuard.mark("wellbeing_followup", profile, concern.day)

        message = WellbeingFollowUpNotifier._message(runner.name, concern)

        await CoachOutbox.send(
            runner, message, profile=profile, kind="wellbeing_followup",
        )

    @staticmethod
    def _message(name: str, concern) -> str:
        """Pergunta acolhedora — doença ou dor. Convida a responder; a resposta
        é tratada pelo cérebro do coach."""

        if concern.illness:

            return (
                f"Oi, {name}! Uns dias atrás você comentou que estava doente "
                "(gripe/resfriado). Como você está se sentindo hoje? 🤎\n\n"
                "Se já passou, a gente retoma com um trote bem leve quando você "
                "quiser — sem pressa. Se ainda não estiver 100%, descansa mais "
                "um pouco que não tem problema."
            )

        # dor
        onde = f" ({concern.note})" if concern.note else ""

        return (
            f"Oi, {name}! Você comentou uma dor{onde} há alguns dias. Como está "
            "agora? 🤔\n\n"
            "Se melhorou, seguimos com o plano numa boa. Se ainda incomoda, "
            "vale pegar leve e, se persistir, dar uma olhada com um "
            "profissional — melhor prevenir."
        )
