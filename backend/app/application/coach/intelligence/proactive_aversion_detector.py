"""Detector PROATIVO de aversão (Fatia 2): depois de cada treino, vê se está
virando PADRÃO o atleta evitar um estímulo de qualidade (rebaixar o tipo ou
furar o pace). Se 3 dos últimos 4 treinos da família vieram evitados, ABRE
uma conversa — NUNCA muda o plano sozinho (um treino ruim não muda o plano; o
ajuste, se houver, vem da negociação REATIVA quando o atleta responde). Um bom
treino da família zera o gatilho (o padrão quebrou)."""

from app.application.coach.intelligence.stimulus_avoidance_evaluator import (
    StimulusAvoidanceEvaluator,
)
from app.core.clock import today_local
from app.domain.entities.enriched_activity import EnrichedActivity
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.stimulus_miss_repository import (
    StimulusMissRepository,
)

# 3 dos últimos 4 treinos da família vieram evitados
_WINDOW = 4

_MIN_AVOIDED = 3

_FAMILY_LABEL = {
    "SPEED": "de velocidade (tiros/intervalados)",
    "TEMPO": "de ritmo (tempo/limiar)",
}


class ProactiveAversionDetector:

    @staticmethod
    def after_feedback(
        runner: RunnerProfile,
        planned: PlannedSession | None,
        executed: EnrichedActivity,
    ) -> str | None:
        """Devolve a mensagem que ABRE a conversa (pro caller enviar) ou
        None. Não muda o plano nem envia nada por conta própria."""

        # Aversão adapta o plano do RunMind; treinador externo tem plano
        # próprio — não puxamos essa conversa com ele.
        if getattr(runner, "external_coach", False):

            return None

        verdict = StimulusAvoidanceEvaluator.evaluate(planned, executed)

        if verdict is None:

            return None

        family, avoided = verdict

        repo = StimulusMissRepository()

        repo.record(
            runner.id,
            family,
            ProactiveAversionDetector._date(executed),
            avoided,
        )

        # Bom treino da família: o padrão quebrou -> rearma o gatilho e sai.
        if not avoided:

            repo.set_nudged(runner.id, family, False)

            return None

        recent = repo.recent_avoided(runner.id, family, _WINDOW)

        pattern = len(recent) >= _WINDOW and sum(recent) >= _MIN_AVOIDED

        # sem padrão ainda, ou já puxamos essa conversa (só volta a valer
        # depois de um bom treino, que rearma o gatilho acima)
        if not pattern or repo.is_nudged(runner.id, family):

            return None

        repo.set_nudged(runner.id, family, True)

        return ProactiveAversionDetector._message(runner.name, family)

    @staticmethod
    def _date(executed: EnrichedActivity) -> str:

        try:

            return executed.activity.start_date.date().isoformat()

        except AttributeError:

            return today_local().isoformat()

    @staticmethod
    def _message(name: str, family: str) -> str:

        label = _FAMILY_LABEL.get(family, "de qualidade")

        return (
            f"Ei, {name}! 👀 Reparei que os últimos treinos {label} não "
            "estão saindo como o plano pede — vêm mais leves que o alvo. "
            "Um dia ou outro é normal, mas quando vira padrão eu prefiro "
            "entender o porquê antes de seguir empurrando a mesma coisa.\n\n"
            "Tem algo nesses treinos que não tá rolando? (não curte, tá "
            "pesado demais, falta de tempo, alguma dor...) Me conta que a "
            "gente ajusta juntos. 💪"
        )
