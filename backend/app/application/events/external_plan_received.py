from app.application.external_plan.external_plan_extraction_engine import (
    ExternalPlanExtractionEngine,
)
from app.application.external_plan.external_plan_service import (
    ExternalPlanService,
)
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.use_cases.load_runner_profile import (
    LoadRunnerProfile,
)
from app.infrastructure.integrations.media_download import (
    download_media,
)

UNREADABLE_REPLY = (
    "Hmm, não consegui ler o treino nessa imagem. 😕 "
    "Consegue mandar uma foto mais nítida (ou o PDF) do plano?"
)


class ExternalPlanEvent:
    """Atleta com treinador humano mandou print/foto/PDF do treino:
    extrai as sessões e registra o plano da semana."""

    @staticmethod
    async def execute(
        profile: str,
        media: dict,
    ) -> str:

        runner = LoadRunnerProfile.execute(profile)

        media_bytes, mimetype = await download_media(
            runner.channel,
            media,
        )

        sessions = await ExternalPlanExtractionEngine.extract(
            media_bytes,
            media.get("mimetype") or mimetype,
        )

        plan = ExternalPlanService.apply(
            profile,
            runner,
            sessions,
        )

        if plan is None:

            reply = UNREADABLE_REPLY

        else:

            sessions_block = "\n".join(
                WeeklyPlanMessageFormatter.session_lines(plan),
            )

            reply = (
                "Plano do seu treinador registrado! ✅\n\n"
                f"{sessions_block}\n\n"
                "Vou acompanhar esses treinos e te dar feedback a cada "
                "um. Se o plano tem mais dias, é só mandar os outros "
                "prints que eu vou somando. Corrigiu algum dia? Manda a "
                "foto de novo que eu atualizo."
            )

        await NotificationService.send(
            runner,
            reply,
        )

        return reply
