"""Fecha o loop da evolução: quando a forma sobe de forma sustentada, o VDOT
(fonte dos paces) sobe sozinho — e o coach AVISA o atleta que ficou mais rápido
e mostra os ritmos novos. Só quando o ganho é REAL (limiar de VDOT) e uma vez
por marco (marca-d'água), pra não repetir. Ver [[project_modelo_pace_vdot]]."""

from app.application.history.pace_model_builder import PaceModelBuilder
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.pace_progress_store import (
    PaceProgressStore,
)

# ganho de VDOT que já vale um aviso (≈ 8–10 s/km mais rápido no limiar)
_VDOT_GAIN = 1.5


class PaceProgressNotifier:

    @staticmethod
    def check(
        profile: str,
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> str | None:
        """Mensagem de "você ficou mais rápido" quando o VDOT subiu além do
        último marco; None caso contrário. Na 1ª vez só grava a base (sem
        avisar — não há com o que comparar)."""

        model = PaceModelBuilder.build(history, runner)

        if model.vdot is None:

            return None

        store = PaceProgressStore()

        last = store.last_vdot(profile)

        if last is None:

            store.save(profile, model.vdot)

            return None

        if model.vdot - last < _VDOT_GAIN:

            return None

        store.save(profile, model.vdot)

        return PaceProgressNotifier._message(runner.name, model)

    @staticmethod
    def _message(name: str, model) -> str:

        def p(pace: float) -> str:

            return PaceFormatter.format(pace)

        return (
            f"🚀 Você ficou mais rápido, {name}! Tua forma subiu de forma "
            "consistente, então reancorei teus ritmos de treino no teu nível "
            "novo. Agora você treina nestes:\n"
            f"• Fácil: {p(model.easy_min)}–{p(model.easy_max)}/km\n"
            f"• Limiar: {p(model.threshold)}/km\n"
            f"• VO₂ / tiros: {p(model.interval)}/km\n\n"
            'Manda "minhas zonas de pace" pra ver a tabela completa. Isso é '
            "evolução virando velocidade. 👊"
        )
