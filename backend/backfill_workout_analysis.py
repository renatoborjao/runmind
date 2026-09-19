"""Backfill das ANÁLISES do coach por atividade — pra a tela da atividade no app
já mostrar a análise dos treinos JÁ realizados (não só dos futuros).

Reprocessa os treinos de corrida de cada atleta (hoje por padrão, ou os últimos
N dias) pela MESMA engine do pós-treino (TrainingPipeline) e GRAVA a análise no
WorkoutAnalysisRepository — reusando a gravação do evento real
(TrainingCompletedEvent._record_analysis), texto limpo, idempotente por
atividade. NÃO envia nada ao atleta (não é o evento, é só a análise+gravação);
pula a prova-alvo (quem conduz lá é o debrief).

⚠ Só é fiel onde os dados estão VIVOS (produção, na Oracle). Numa cópia local
defasada, reprocessa o que houver de sync local. Roda 1 chamada de Gemini por
treino (a análise da IA) — janela curta (hoje) mantém o custo baixo.

Uso:
  python backfill_workout_analysis.py                 # todos, só hoje
  python backfill_workout_analysis.py <profile>       # um atleta, só hoje
  python backfill_workout_analysis.py <profile> --days 7   # últimos 7 dias
  python backfill_workout_analysis.py --dry-run       # não grava, só mostra
"""

import argparse
import asyncio
from datetime import timedelta

from app.application.events.training_completed import TrainingCompletedEvent
from app.application.coach.intelligence.race_debrief import RaceDebrief
from app.application.orchestrators.training_pipeline import TrainingPipeline
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import today_local, use_athlete_timezone
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

_RUN_HINT = ("run", "corrida", "trail")


def _is_run(sport: str) -> bool:

    return any(h in (sport or "").lower() for h in _RUN_HINT)


def _recent_runs(profile: str, days: int) -> list:
    """Corridas do atleta nos últimos `days` dias (no fuso dele), mais recentes
    primeiro. days=1 = só hoje."""

    runner = LoadRunnerProfile.execute(profile)

    use_athlete_timezone(runner.timezone)

    cutoff = today_local() - timedelta(days=days - 1)

    runs = [
        a
        for a in ActivityArchiveRepository().load_activities(profile)
        if _is_run(a.sport) and a.start_date.date() >= cutoff
    ]

    runs.sort(key=lambda a: a.start_date, reverse=True)

    return runs


async def _backfill_profile(profile: str, days: int, dry_run: bool) -> int:

    runs = _recent_runs(profile, days)

    if not runs:

        return 0

    done = 0

    for activity in runs:

        try:

            result = await TrainingPipeline.execute(profile, activity)

        except Exception as e:

            print(f"  ! {profile} {activity.start_date.date()} "
                  f"({activity.id}): pipeline falhou: {e}")

            continue

        if RaceDebrief.is_target_race(result["runner"], result["activity"]):

            print(f"  · {profile} {activity.start_date.date()}: prova — pulada")

            continue

        km = round((activity.distance or 0) / 1000, 2)

        if dry_run:

            print(f"  [dry] {profile} {activity.start_date.date()} "
                  f"{km}km ({activity.id}): análise pronta ({len(result['message'])} chars)")

        else:

            TrainingCompletedEvent._record_analysis(
                profile, result, result["message"]
            )

            print(f"  ✓ {profile} {activity.start_date.date()} "
                  f"{km}km ({activity.id}): análise gravada")

        done += 1

    return done


async def _run(profile: str | None, days: int, dry_run: bool) -> None:

    profiles = (
        [profile]
        if profile
        else sorted(RunnerProfileRepository().list_all())
    )

    total = 0

    for p in profiles:

        print(f"» {p}")

        total += await _backfill_profile(p, days, dry_run)

    verb = "seriam gravadas" if dry_run else "gravadas"

    print(f"\n{total} análise(s) {verb} (janela: {days} dia(s)).")


def main() -> None:

    parser = argparse.ArgumentParser(description="Backfill de análises do coach.")

    parser.add_argument("profile", nargs="?", default=None,
                        help="perfil (omita para todos)")

    parser.add_argument("--days", type=int, default=1,
                        help="janela em dias (1 = só hoje)")

    parser.add_argument("--dry-run", action="store_true",
                        help="não grava, só mostra o que faria")

    args = parser.parse_args()

    asyncio.run(_run(args.profile, args.days, args.dry_run))


if __name__ == "__main__":

    main()
