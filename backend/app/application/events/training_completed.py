from app.application.coach.intelligence.personal_record_detector import (
    PersonalRecordDetector,
)
from app.application.coach.intelligence.proactive_aversion_detector import (
    ProactiveAversionDetector,
)
from app.application.notifications.coach_outbox import (
    CoachOutbox,
)
from app.application.orchestrators.training_pipeline import (
    TrainingPipeline,
)
from app.domain.entities.activity import (
    Activity,
)


class TrainingCompletedEvent:

    @staticmethod
    async def execute(
        profile: str = "renato",
        activity: Activity | None = None,
    ):

        result = await TrainingPipeline.execute(
            profile=profile,
            activity=activity,
        )

        runner = result["runner"]

        # CoachOutbox: envia E registra no outbox (pra o coach lembrar da
        # análise quando o atleta comentar depois no chat)
        await CoachOutbox.send(
            runner,
            result["message"],
        )

        # Detector proativo de aversão (Fatia 2): depois do feedback, se está
        # virando PADRÃO evitar um estímulo de qualidade, ABRE uma conversa —
        # nunca muda o plano. Falha aqui jamais derruba o feedback já enviado.
        try:

            nudge = ProactiveAversionDetector.after_feedback(
                runner,
                result["planned_session"],
                result["activity"],
            )

            if nudge:

                await CoachOutbox.send(runner, nudge)

        except Exception as e:

            print(f"Falha no detector proativo de aversão: {e}")

        # Celebração de PR/marcos: reconhece recorde batido (corrida mais
        # longa, treino mais rápido na faixa, km acumulado, semana de maior
        # volume). Vale pra TODOS os atletas, inclusive treinador externo —
        # não mexe no plano, só comemora. Falha aqui jamais derruba o
        # feedback já enviado.
        try:

            celebration = PersonalRecordDetector.after_feedback(
                runner,
                result["history"],
                result["activity"],
            )

            if celebration:

                await CoachOutbox.send(runner, celebration)

        except Exception as e:

            print(f"Falha na celebração de recorde: {e}")

        return result