"""Fecha o loop da evolução: quando o atleta fica mais rápido, o coach AVISA e
mostra os ritmos novos. Dois caminhos, ambos com marca-d'água (um aviso por
marco, nunca repete):

1. CAPACIDADE — o VDOT (teto) sobe além do último marco → reancoragem completa
   (todos os ritmos mudam).
2. FÁCIL — o ritmo fácil evolui pela ÂNCORA DE REALIDADE (corridas recentes
   ficaram mais soltas no mesmo conforto) mesmo com o VDOT estável → aviso
   focado no fácil. Sem isto, o fácil ficava mais rápido no silêncio (gap que a
   janela recente de [[project_modelo_pace_vdot]] abriu).

Só avisa MELHORA (nunca "ficou mais lento") e só quando é relevante. Watermark
do fácil = o mais rápido já avisado (não recua com oscilação)."""

from app.application.history.pace_model_builder import PaceModelBuilder
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.pace_progress_store import (
    PaceProgressStore,
)

# ganho de VDOT que já vale um aviso (≈ 8–10 s/km mais rápido no limiar)
_VDOT_GAIN = 1.5

# queda do fácil (min/km) que já vale um aviso: ~8 s/km. Mesma ordem do ganho de
# VDOT — só notícia de verdade, não ruído de amostragem semana a semana.
_EASY_GAIN = 0.13


class PaceProgressNotifier:

    @staticmethod
    def check(
        profile: str,
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> str | None:
        """Mensagem de "você ficou mais rápido" quando o VDOT subiu OU o fácil
        evoluiu além do último marco; None caso contrário. Na 1ª vez só grava a
        base (sem avisar — não há com o que comparar)."""

        model = PaceModelBuilder.build(history, runner)

        if model.vdot is None:

            return None

        store = PaceProgressStore()

        last_vdot = store.last_vdot(profile)

        last_easy = store.last_easy_min(profile)

        # 1ª vez absoluta: grava a base dos dois marcos, não avisa
        if last_vdot is None:

            store.save(profile, model.vdot, model.easy_min)

            return None

        # watermark do fácil preservado (só desce = mais rápido)
        def easy_mark() -> float:

            if last_easy is None:

                return model.easy_min

            return min(model.easy_min, last_easy)

        # CAPACIDADE subiu: reancoragem completa (a msg já mostra o fácil novo)
        if model.vdot - last_vdot >= _VDOT_GAIN:

            store.save(profile, model.vdot, easy_mark())

            return PaceProgressNotifier._message(runner.name, model)

        # só o FÁCIL evoluiu (âncora de realidade), VDOT estável
        if last_easy is not None and (last_easy - model.easy_min) >= _EASY_GAIN:

            store.save(profile, last_vdot, model.easy_min)

            return PaceProgressNotifier._easy_message(runner.name, model)

        # arquivo antigo sem marco do fácil: grava a base dele agora (sem avisar)
        if last_easy is None:

            store.save(profile, last_vdot, model.easy_min)

        return None

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

    @staticmethod
    def _easy_message(name: str, model) -> str:

        def p(pace: float) -> str:

            return PaceFormatter.format(pace)

        return (
            f"🚀 Teu ritmo fácil ficou mais rápido, {name}! Tuas corridas das "
            "últimas semanas mostram que você segura um pace mais solto com o "
            "mesmo conforto, então ajustei teu fácil pro teu nível atual:\n"
            f"• Fácil: {p(model.easy_min)}–{p(model.easy_max)}/km\n\n"
            "Os treinos de qualidade seguem no mesmo alvo — isso aqui é a tua "
            'base ficando mais forte. 👊 (manda "minhas zonas" pra ver tudo)'
        )
