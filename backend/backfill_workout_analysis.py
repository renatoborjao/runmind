"""Backfill das ANÁLISES do coach por atividade — pra a tela da atividade no app
já mostrar a análise dos treinos JÁ realizados (não só dos futuros).

Pra cada treino de corrida (hoje por padrão, ou os últimos N dias) grava a
análise no WorkoutAnalysisRepository. FONTE, em ordem de preferência:

1. **Mensagem canônica do outbox** — o feedback que o coach REALMENTE enviou
   naquele dia (com "🧩 Execução por bloco" e "⏱️ Parciais por km", porque foi
   gerada com os splits do Garmin). Casa por data + distância executada, corta as
   caudas de chat (pergunta de RPE 💬 e nota de tênis 👟) e grava só a análise.
   Idêntica à aba Coach; não gasta Gemini.

2. **Regeneração pelo pipeline** — só quando não há feedback canônico no outbox
   (treino antigo que já saiu das últimas mensagens). O arquivo reduzido não tem
   splits, então essa versão é mais pobre (sem blocos/parciais) — fallback.

NÃO envia nada ao atleta; pula a prova-alvo (lá quem conduz é o debrief).

Uso:
  python backfill_workout_analysis.py                 # todos, só hoje
  python backfill_workout_analysis.py <profile>       # um atleta, só hoje
  python backfill_workout_analysis.py <profile> --days 7   # últimos 7 dias
  python backfill_workout_analysis.py --dry-run       # não grava, só mostra
"""

import argparse
import asyncio
import re
from datetime import timedelta

from app.application.coach.analysis_cleaner import AnalysisCleaner
from app.application.events.training_completed import TrainingCompletedEvent
from app.application.coach.intelligence.race_debrief import RaceDebrief
from app.application.orchestrators.training_pipeline import TrainingPipeline
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import today_local, use_athlete_timezone
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.coach_outbox_repository import (
    CoachOutboxRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.workout_analysis_repository import (
    WorkoutAnalysisRepository,
)

_RUN_HINT = ("run", "corrida", "trail")


def _is_run(sport: str) -> bool:

    return any(h in (sport or "").lower() for h in _RUN_HINT)


def _planned_type(text: str) -> str | None:
    """Tipo do treino a partir do bloco '📅 Planejado' do feedback (o bullet que
    não é data nem distância). Best-effort — None se não achar."""

    m = re.search(r"📅 Planejado\n((?:•.*\n?)+)", text)

    if not m:

        return None

    for line in m.group(1).splitlines():

        s = line.lstrip("• ").strip()

        if not s:

            continue

        # pula a data "sábado (19/09)" e a distância "15.0 km"
        if "(" in s and "/" in s:

            continue

        if re.search(r"\d", s) and "km" in s:

            continue

        return s

    return None


def _feedback_core_from_outbox(profile: str, activity) -> str | None:
    """Análise CANÔNICA deste treino a partir do outbox: o feedback enviado cuja
    data (dd/mm) e distância executada casam com a atividade. Devolve só a análise
    (sem caudas), ou None quando não há feedback correspondente guardado."""

    km = (activity.distance or 0) / 1000

    d = activity.start_date.date()

    date_tag = f"({d.day:02d}/{d.month:02d})"

    for entry in reversed(CoachOutboxRepository().recent(profile, 50)):

        text = entry.get("text", "")

        if "Executado" not in text or date_tag not in text:

            continue

        m = re.search(r"Dist[âa]ncia:\s*([\d.,]+)\s*km", text)

        if not m:

            continue

        executed_km = float(m.group(1).replace(",", "."))

        if abs(executed_km - km) <= 0.2:

            return AnalysisCleaner.clean(text)

    return None


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

    repo = WorkoutAnalysisRepository()

    done = 0

    for activity in runs:

        date = activity.start_date.date().isoformat()

        km = round((activity.distance or 0) / 1000, 2)

        # 1) FONTE CANÔNICA: o feedback que o coach enviou (com blocos/parciais)
        core = _feedback_core_from_outbox(profile, activity)

        if core:

            if dry_run:

                print(f"  [dry·outbox] {profile} {date} {km}km ({activity.id}): "
                      f"análise canônica ({len(core)} chars)")

            else:

                repo.record(
                    profile,
                    activity_id=activity.id,
                    date=date,
                    distance_km=km,
                    analysis=core,
                    workout_type=_planned_type(core),
                )

                print(f"  ✓ outbox {profile} {date} {km}km ({activity.id})")

            done += 1

            continue

        # 2) FALLBACK: regenera (sem splits — mais pobre) só quando não há canônica
        try:

            result = await TrainingPipeline.execute(profile, activity)

        except Exception as e:

            print(f"  ! {profile} {date} ({activity.id}): pipeline falhou: {e}")

            continue

        if RaceDebrief.is_target_race(result["runner"], result["activity"]):

            print(f"  · {profile} {date}: prova — pulada")

            continue

        if dry_run:

            print(f"  [dry·regen] {profile} {date} {km}km ({activity.id}): "
                  f"análise regenerada ({len(result['message'])} chars)")

        else:

            TrainingCompletedEvent._record_analysis(
                profile, result, result["message"]
            )

            print(f"  ✓ regen  {profile} {date} {km}km ({activity.id})")

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
