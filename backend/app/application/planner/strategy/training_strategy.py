from app.domain.entities.training_assessment import TrainingAssessment


# Volume relativo por fase do ciclo (ancorado na prova):
# BASE/BUILD carregam volume; PICO afia (menos volume, mais intensidade —
# intensidade fica pra frente 1.2); TAPER poli pra chegar descansado.
PHASE_VOLUME_FACTOR = {
    "BASE": 1.0,
    "BUILD": 1.0,
    "PEAK": 0.9,
    "TAPER": 0.6,
}

# Semana de corte (deload) do ciclo 3:1: reduz pra assimilar a carga.
DELOAD_VOLUME_FACTOR = 0.8


class TrainingStrategy:

    @staticmethod
    def build(
        assessment: TrainingAssessment,
        phase: str = "BUILD",
        is_deload: bool = False,
        base_volume: float | None = None,
    ) -> dict:

        factor = PHASE_VOLUME_FACTOR.get(phase, 1.0)

        if is_deload:

            factor *= DELOAD_VOLUME_FACTOR

        # base_volume = alvo da progressão (fiel ao histórico); sem ele,
        # cai no volume recomendado do assessment (caminho antigo).
        base = (
            base_volume
            if base_volume is not None
            else assessment.recommended_weekly_volume
        )

        weekly_volume = round(
            base * factor,
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