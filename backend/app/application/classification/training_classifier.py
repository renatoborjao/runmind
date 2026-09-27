from app.application.classification.training_classification import (
    TrainingClassification,
)
from app.application.classification.training_score import (
    TrainingScore,
)
from app.application.classification.workout_type import (
    WorkoutType,
)
from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.runner_metrics import (
    RunnerMetrics,
)
from app.domain.entities.workout_structure import (
    WorkoutStructure,
)


# Piso absoluto para pontuar como longão: sem isso, um histórico
# minúsculo (max_long_run de 100 m) faz qualquer trote virar LONG_RUN.
# Abaixo de 10 km não é longão, independente do histórico.
MIN_LONG_RUN_KM = 10.0

# Estrutura de tiros vence o retrato médio: sem isso, o intervalado se
# dilui na média e vira "rodagem leve" (média de tiro + pausa).
INTERVAL_STRUCTURE_POINTS = 80

# Pesos: pace e FC são os juízes da intensidade (empatados); a faixa moderada
# (entre limiar e leve) é ambígua e divide os pontos entre rodagem e ritmo.
# Empate cai no MENOS intenso (ordem da lista de scores).
PACE_POINTS = 35
MODERATE_PACE_POINTS = 15
HR_POINTS = 35
# FC só relativa à média de costume (sem régua de zonas) é sinal fraco
RELATIVE_HR_POINTS = 15

# Longão: distância típica do atleta (≥90% do maior e ≥10 km) vence a
# intensidade de rodagem; a duração longa reforça.
LONG_RUN_DISTANCE_POINTS = 75
LONG_RUN_DURATION_POINTS = 30
LONG_RUN_MINUTES = 90


class TrainingClassifier:

    @staticmethod
    def classify(
        activity: EnrichedActivity,
        metrics: RunnerMetrics,
        structure: WorkoutStructure | None = None,
    ) -> TrainingClassification:

        distance = activity.activity.distance / 1000

        pace = activity.pace_min_km

        duration = activity.activity.moving_time / 60

        scores = [

            TrainingScore(WorkoutType.RECOVERY),

            TrainingScore(WorkoutType.EASY),

            TrainingScore(WorkoutType.TEMPO),

            TrainingScore(WorkoutType.VO2),

            TrainingScore(WorkoutType.LONG_RUN),

            TrainingScore(WorkoutType.INTERVAL),

        ]

        # O TIPO sai da INTENSIDADE (pace nas faixas do atleta + zona de FC na
        # régua dele); distância/duração só dizem se é LONGÃO e a estrutura de
        # tiros diz se é INTERVALADO. Antes "8 km" e "54 min" pontuavam como
        # Ritmo e uma rodagem leve (pace no alvo, FC em Z2) saía "Ritmo" —
        # bug do Renato 25/09. Ver [[project_zonas_fc_regua_unica]].

        # ---------------- PACE ----------------

        if pace <= 0:

            pass  # sem pace (esteira sem sensor): só a FC fala

        elif pace <= metrics.vo2_pace:

            scores[3].add(PACE_POINTS, "Pace de VO2")

        elif pace <= metrics.threshold_pace:

            scores[2].add(PACE_POINTS, "Pace de limiar")

        elif pace < metrics.easy_pace_min:

            # entre o limiar e o leve: AMBÍGUO (a faixa leve do plano pode ser
            # conservadora) — o pace não decide sozinho, a FC desempata (Z4+
            # vira ritmo; Z2/Z3 segue rodagem)
            scores[1].add(MODERATE_PACE_POINTS, "Pace moderado")

            scores[2].add(MODERATE_PACE_POINTS, "Pace moderado")

        elif pace <= metrics.easy_pace_max:

            scores[1].add(PACE_POINTS, "Pace confortável")

        else:

            scores[0].add(PACE_POINTS, "Pace regenerativo")

        # ---------------- FC ----------------

        TrainingClassifier._score_hr(scores, activity, metrics)

        # ---------------- LONGÃO (distância/duração) ----------------

        if (
            distance >= metrics.max_long_run * 0.90
            and distance >= MIN_LONG_RUN_KM
        ):

            scores[4].add(
                LONG_RUN_DISTANCE_POINTS,
                "Distância típica de longão",
            )

            if duration >= LONG_RUN_MINUTES:

                scores[4].add(
                    LONG_RUN_DURATION_POINTS,
                    "Treino longo",
                )

        # ---------------- ESTRUTURA (splits/voltas) ----------------

        # Tiros alternados detectados no detalhe do treino: sinal forte
        # e decisivo, sobrepõe o retrato médio que apagaria o intervalado.
        if structure is not None and structure.is_interval:

            scores[5].add(
                INTERVAL_STRUCTURE_POINTS,
                "Tiros alternados nos splits/voltas",
            )

        winner = max(
            scores,
            key=lambda s: s.score,
        )

        confidence = min(
            winner.score / 100,
            0.99,
        )

        return TrainingClassification(

            workout_type=winner.workout,

            intensity=activity.intensity,

            estimated_zone=activity.estimated_zone,

            confidence=confidence,

            reasons=winner.reasons,

        )

    @staticmethod
    def _score_hr(
        scores: list[TrainingScore],
        activity: EnrichedActivity,
        metrics: RunnerMetrics,
    ) -> None:
        """FC média na régua de zonas do atleta ([[HrZoneResolver]]): Z1
        regenerativo, Z2 rodagem, Z3 moderado (pende pra rodagem, reforça
        ritmo), Z4 ritmo, Z5 VO2. Sem régua, cai na FC relativa à média de
        costume com peso baixo. Sem FC real, não pontua."""

        hr = activity.activity.average_heartrate

        if not hr:

            return

        zones = metrics.hr_zones

        if zones is not None:

            zone = zones.zone_of(hr) or 1

            if zone == 1:

                scores[0].add(HR_POINTS, "FC em Z1")

            elif zone == 2:

                scores[1].add(HR_POINTS, "FC em Z2")

            elif zone == 3:

                scores[1].add(HR_POINTS // 2, "FC em Z3")

                scores[2].add(HR_POINTS // 2, "FC em Z3")

            elif zone == 4:

                scores[2].add(HR_POINTS, "FC em Z4")

            else:

                scores[3].add(HR_POINTS, "FC em Z5")

            return

        usual = metrics.average_hr

        if not usual:

            return

        if hr >= usual + 15:

            scores[3].add(RELATIVE_HR_POINTS, "FC muito acima do costume")

        elif hr >= usual + 8:

            scores[2].add(RELATIVE_HR_POINTS, "FC acima do costume")

        elif hr >= usual - 5:

            scores[1].add(RELATIVE_HR_POINTS, "FC no costume")

        else:

            scores[0].add(RELATIVE_HR_POINTS, "FC abaixo do costume")
