"""Reproduz OFFLINE a mensagem que o atleta recebe em 'como está minha forma'
(FITNESS_TREND), pra validar a redação com dado real antes de deployar.

Uso: python show_fitness.py <profile>
"""

import sys

from app.application.coach.conversation.on_demand_answers import OnDemandAnswers
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.coach.intelligence.progress_report import ProgressReport
from app.application.coach.writer.fitness_evolution_writer import (
    FitnessEvolutionWriter,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import use_athlete_timezone


def main(profile: str) -> None:

    runner = LoadRunnerProfile.execute(profile)

    use_athlete_timezone(runner.timezone)

    evolution = FitnessReadingService.read_evolution(profile)

    print("=== DIAGNÓSTICO (interno) ===")
    print(f"  direction={evolution.direction} confidence={evolution.confidence}")
    print(
        f"  vo2max_trend={'SIM' if evolution.vo2max else 'None'} "
        f"points={evolution.vo2max_points} "
        f"last_days={evolution.vo2max_last_days} "
        f"span={evolution.vo2max_span_days} frozen={evolution.vo2max_frozen}"
    )
    if evolution.ef:
        print(
            f"  EF: weeks_covered={evolution.ef.weeks_covered} "
            f"pace_gain={evolution.ef.pace_gain_sec} ref_hr={evolution.ef.ref_hr}"
        )
    print()

    evo_msg = FitnessEvolutionWriter.write(evolution, runner.name)

    from app.application.coach.writer.race_prediction_writer import (
        RacePredictionWriter,
    )
    from app.infrastructure.persistence.race_prediction_repository import (
        RacePredictionRepository,
    )

    race_block = RacePredictionWriter.block(
        RacePredictionRepository().load(profile)
    )

    progress = ProgressReport.build(profile)

    parts = [p for p in (evo_msg, race_block, progress) if p]

    parts.append(OnDemandAnswers._FORM_TO_BODY_BRIDGE)

    print("=== MENSAGEM 'COMO ESTÁ MINHA FORMA' (como o atleta recebe) ===")
    print()
    print("\n\n".join(parts))
    print()


if __name__ == "__main__":

    main(sys.argv[1] if len(sys.argv) > 1 else "renato2")
