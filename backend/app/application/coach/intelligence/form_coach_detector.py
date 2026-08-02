"""Coaching de FORMA/economia: quando a cadência do atleta está claramente
baixa, manda UMA dica acionável (passos mais curtos e rápidos ~170-175) — a
alavanca clássica de economia e menos lesão que ninguém no grátis faz bem.

Regra (item 26 de [[project_ideias_produto]]): só aponta quando o sinal é CLARO
e ACIONÁVEL, nunca polui com métrica solta. Uma vez por atleta (dedup) — não
vira spam a cada corrida. Separado do feedback (não mexe no plano), best-effort.
GCT/oscilação vertical: refino futuro (subir a cadência já melhora os dois)."""

from app.domain.entities.enriched_activity import EnrichedActivity
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.persistence.dispatch_guard import DispatchGuard

_KIND = "form_cadence"

# abaixo disto a cadência é claramente baixa (recreativo ~160-170; alvo ~170-180)
_LOW_CADENCE_SPM = 163

# corrida de verdade (fragmento curto não representa a cadência)
_MIN_KM = 3.0

# mais lento que isto é trote/caminhada — cadência baixa é natural, não coacha
_WALK_PACE = 7.5  # min/km


class FormCoachDetector:

    @staticmethod
    def after_feedback(
        profile: str,
        runner: RunnerProfile,
        enriched: EnrichedActivity | None,
    ) -> str | None:

        if enriched is None or enriched.structure is None:

            return None

        cadence = enriched.structure.cadence_spm

        activity = enriched.activity

        if cadence is None or not is_run_sport(activity.sport):

            return None

        if activity.distance / 1000 < _MIN_KM:

            return None

        # em ritmo de trote/caminhada, cadência baixa é esperada — não coacha
        if enriched.pace_min_km > _WALK_PACE:

            return None

        if cadence >= _LOW_CADENCE_SPM:

            return None

        # uma vez por atleta: a dica é educativa, repetir a cada corrida cansa
        if DispatchGuard.already_sent(_KIND, profile, "v1"):

            return None

        DispatchGuard.mark(_KIND, profile, "v1")

        return FormCoachDetector._nudge(runner.name, cadence)

    @staticmethod
    def _nudge(name: str, cadence: int) -> str:

        return (
            f"👟 Uma dica de forma, {name}: sua cadência hoje foi ~{cadence} "
            "passos/min. Mirar 170-175 — passos um pouco mais curtos e "
            "rápidos, sem forçar o ritmo — reduz o impacto a cada passada, te "
            "deixa mais econômico e protege de lesão. É velocidade quase de "
            "graça. 🎯\n\nPra treinar: num trecho da próxima corrida, conte os "
            "passos de UM pé em 30s e multiplique por 4 — mire uns 85-88."
        )
