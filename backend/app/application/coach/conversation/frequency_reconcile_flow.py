"""Resolve a resposta do atleta à oferta de OFICIALIZAR um dia a mais (o coach
perguntou "quer 4 dias?" porque ele treina em rotina além do plano). "SIM" ->
atualiza os dias no perfil; NÃO remexe a semana ATUAL (mudança estrutural entra
no plano da PRÓXIMA semana, gerado no domingo) — sem regen na hora, sem oferta
de relógio (nada mudou nesta semana); "não" -> mantém e reconhece. Só age quando
há uma oferta PENDENTE (o "sim" é sobre isso, não uma afirmação solta).

Ver [[project_reconciliacao_coach]] e [[project_preferencia_duravel_rotina]]."""

from app.application.coach.conversation.proposal_reply_detector import (
    ProposalReply,
    ProposalReplyDetector,
)
from app.core.weekdays import weekday_label
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.frequency_offer_store import (
    FrequencyOfferStore,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

_WEEKDAY_ORDER = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday",
]


class FrequencyReconcileFlow:

    @staticmethod
    async def resolve_reply(
        profile: str, runner: RunnerProfile, incoming_text: str
    ) -> str | None:
        """None quando não há oferta pendente OU a resposta é ambígua (aí outros
        handlers/o chat seguem, e a oferta continua viva)."""

        pending = FrequencyOfferStore.get_pending(profile)

        if pending is None:

            return None

        reply = ProposalReplyDetector.detect(incoming_text)

        if reply == ProposalReply.UNCLEAR:

            return None

        FrequencyOfferStore.clear(profile)

        reg = len(runner.preferred_running_days)

        if reply == ProposalReply.REJECT:

            return (
                f"Beleza, {runner.name}! Mantenho teu plano em {reg} dias — o "
                "treino extra fica livre, à tua vontade. 👊"
            )

        # CONFIRM: oficializa o dia
        weekday = pending.get("weekday")

        new_days = FrequencyReconcileFlow._add_day(
            runner.preferred_running_days, weekday
        )

        RunnerProfileRepository().update_fields(
            profile,
            {
                "preferred_running_days": new_days,
                "weekly_training_days": len(new_days),
            },
        )

        dia = weekday_label(weekday) if weekday else ""

        extra = f" teu {dia}" if dia else ""

        # oficializa o dia no perfil, mas NÃO remexe a semana ATUAL (ela já está
        # rolando — mudança estrutural entra no plano da PRÓXIMA semana, gerado
        # no domingo). Sem regeneração agora, sem oferta de relógio (nada mudou
        # nesta semana). Ver [[project_preferencia_duravel_rotina]].
        if runner.external_coach:

            return (
                f"Fechou, {runner.name}! Anotei{extra} — teu plano passa a ser "
                f"{len(new_days)} dias/semana. 💪"
            )

        return (
            f"Isso, {runner.name}! Oficializei{extra} — teu plano passa a ser "
            f"{len(new_days)} dias/semana. Não mexo na tua semana atual (já tá "
            "rolando); a partir de domingo eu já monto o plano contando com "
            "ele. 💪"
        )

    @staticmethod
    def _add_day(days: list[str], weekday: str | None) -> list[str]:
        """Adiciona o dia (dedup) e reordena Seg..Dom. Sem dia claro, devolve a
        lista como está (não inventa)."""

        current = list(days or [])

        if weekday and weekday not in current:

            current.append(weekday)

        return sorted(
            current,
            key=lambda d: _WEEKDAY_ORDER.index(d)
            if d in _WEEKDAY_ORDER
            else 99,
        )
