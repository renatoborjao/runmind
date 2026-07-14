from app.application.coach.intelligence.proactive_aversion_detector import (
    ProactiveAversionDetector,
)
from app.application.notifications.notification_service import (
    NotificationService,
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

        await NotificationService.send(
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

                await NotificationService.send(runner, nudge)

        except Exception as e:

            print(f"Falha no detector proativo de aversão: {e}")

        return result