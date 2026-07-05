from app.application.external_plan.external_plan_extraction_engine import (
    ExternalPlanExtractionEngine,
)
from app.application.history.plan_baseline_builder import (
    PlanBaselineBuilder,
)
from app.infrastructure.integrations.media_download import download_media
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class ImportPlanBaseline:
    """Importa um plano do atleta (imagem/PDF) e o registra como o
    retrato-base dele: quando o Strava é fino, o motor passa a planejar
    nesse nível em vez de subestimar. Reusa a extração por visão do
    modo treinador."""

    @staticmethod
    async def execute(
        profile: str,
        channel: str,
        media: dict,
    ) -> str:

        try:

            media_bytes, mimetype = await download_media(channel, media)

            sessions = await ExternalPlanExtractionEngine.extract(
                media_bytes,
                media.get("mimetype") or mimetype,
            )

        except Exception as e:

            print(f"Falha ao importar plano de '{profile}': {e}")

            return (
                "Opa, não consegui ler esse plano agora 😅 "
                "Tenta mandar de novo daqui a pouco?"
            )

        seed = PlanBaselineBuilder.from_sessions(sessions)

        if seed is None:

            return (
                "Consegui abrir, mas não achei corridas com distância "
                "nesse plano. Manda um com os km por treino que eu "
                "registro seu nível. 📸"
            )

        RunnerProfileRepository().update_fields(
            profile,
            {"plan_baseline": seed},
        )

        return (
            "Registrei seu nível a partir desse plano! 📈\n\n"
            f"• ~{seed['weekly_km']:.0f} km por semana\n"
            f"• {seed['runs_per_week']} corridas/semana\n"
            f"• longão de {seed['longest_km']:.0f} km\n\n"
            "A partir de agora eu planejo nesse nível e evoluo daqui — "
            "sem te puxar pra baixo."
        )
