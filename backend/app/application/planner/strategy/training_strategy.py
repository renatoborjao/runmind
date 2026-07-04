from app.domain.entities.training_assessment import TrainingAssessment


# Semana de véspera de prova: chega descansado, sem perder o costume.
TAPER_VOLUME_FACTOR = 0.6


class TrainingStrategy:

    @staticmethod
    def build(
        assessment: TrainingAssessment,
        phase: str = "BUILD",
    ) -> dict:

        weekly_volume = assessment.recommended_weekly_volume

        if phase == "TAPER":

            weekly_volume = round(
                weekly_volume * TAPER_VOLUME_FACTOR,
                1,
            )

        # O longão respeita a capacidade real (maior treino já feito),
        # sem saltar demais frente ao volume da semana.
        longest_run = min(
            assessment.longest_run,
            round(
                max(
                    weekly_volume * 0.35,
                    assessment.longest_run * 0.75,
                ),
                1,
            ),
        )

        remaining = weekly_volume - longest_run

        easy_run = round(remaining * 0.45, 1)

        quality_run = round(remaining * 0.55, 1)

        # Iniciante não faz VO2: a sessão de qualidade vira um
        # progressivo (rodagem que acelera no fim), estímulo seguro.
        quality_type = (
            "PROGRESSION"
            if assessment.level == "Beginner"
            else "VO2"
        )

        return {

            "week_type": phase,

            "weekly_volume": weekly_volume,

            "long_run": longest_run,

            "easy_run": easy_run,

            "quality_run": quality_run,

            "quality_type": quality_type,
        }