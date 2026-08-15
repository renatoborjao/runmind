"""Traduz a ESTRATÉGIA de prova (RacePacePlan) em passos estruturados que o
Garmin guia no relógio — blocos de NEGATIVE SPLIT com faixa de pace, do
controlado ao forte. É o "não quebrar" virado treino: o relógio alerta quando o
atleta acelera cedo demais (o erro nº 1 que estoura a prova).

Puro/determinístico. Reusa o `RacePacePlan` do [[RaceStrategyEngine]] e alimenta
o push que já existe ([[garmin_push]]). Ver [[project_treino_avulso]]."""

from app.application.coach.planning.race_strategy_engine import RacePacePlan
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.workout_step import RUN, WorkoutStep

# blocos do negative split: (fração da distância, offset de pace em s/km sobre o
# ritmo médio). Começa CONTROLADO (mais lento) e vai fechando FORTE; a média
# ponderada bate exatamente o pace-alvo. É a espinha do "não quebrar".
_BLOCKS = (
    (0.20, +8),   # largada segura — o freio contra estourar
    (0.30, +3),
    (0.30, -3),
    (0.20, -8),   # esvazia o tanque
)

# meia-largura (s/km) da FAIXA de pace de cada bloco que o relógio mostra/alerta
_ZONE_HALF = 3


class RaceWorkoutComposer:

    @staticmethod
    def compose(plan: RacePacePlan) -> list[WorkoutStep]:
        """Passos de corrida (por distância, com faixa de pace) do controlado ao
        forte, somando a distância da prova e a média do pace-alvo."""

        avg_sec = plan.avg_pace_min * 60  # s/km

        steps: list[WorkoutStep] = []

        for fraction, offset in _BLOCKS:

            distance_m = round(plan.distance_km * fraction * 1000)

            if distance_m <= 0:

                continue

            center = avg_sec + offset

            fast = (center - _ZONE_HALF) / 60  # min/km (ponta rápida)

            slow = (center + _ZONE_HALF) / 60  # min/km (ponta lenta)

            steps.append(
                WorkoutStep(
                    kind=RUN,
                    distance_m=float(distance_m),
                    pace_min=PaceFormatter.format(fast),
                    pace_max=PaceFormatter.format(slow),
                )
            )

        return steps
