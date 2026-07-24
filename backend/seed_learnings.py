"""Backfill do cérebro coach: destila os aprendizados a partir do histórico
que o atleta JÁ tem (aderência + prescrito×executado + resposta do corpo),
sem esperar acumular semana a semana. Roda o MESMO caminho do domingo 20h,
só que na hora.

A Fonte A (correções aceitas) começa vazia — é evento que só passa a ser
capturado daqui pra frente; a base inicial vem das Fontes B e C.

Uso:
  python seed_learnings.py <profile>   # um atleta
  python seed_learnings.py             # todos os atletas
"""

import asyncio
import sys

from app.application.review.weekly_review_notifier import WeeklyReviewNotifier
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import use_athlete_timezone
from app.infrastructure.persistence.coach_learning_repository import (
    CoachLearningRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


async def seed(profile: str) -> None:

    print(f"  {profile}: destilando histórico...", flush=True)

    runner = LoadRunnerProfile.execute(profile)

    use_athlete_timezone(runner.timezone)

    history = await LoadTrainingHistory.execute(profile=profile, limit=60)

    await WeeklyReviewNotifier._distill_learnings(profile, runner, history)

    learned = CoachLearningRepository().active(profile)

    if not learned:

        print(f"  {profile}: nada a aprender ainda (histórico magro)")

        return

    print(f"  {profile}: {len(learned)} aprendizado(s):")

    for entry in learned:

        print(f"    - [{entry.category}] {entry.content}")


async def main() -> None:

    if len(sys.argv) > 1:

        await seed(sys.argv[1])

        return

    for profile in RunnerProfileRepository().list_all():

        await seed(profile)


if __name__ == "__main__":

    asyncio.run(main())
