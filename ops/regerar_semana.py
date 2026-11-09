"""REFAZ a semana que o coach monta (a próxima) de UM atleta com o código ATUAL do coach — roda
na VM, contra os dados REAIS. Um atleta por vez (--profile é obrigatório): nunca refaz todo mundo.

Quando usar: a lógica do coach mudou DEPOIS de o plano de domingo já ter sido gerado e entregue
(Renato, 08/11: o plano das 20:01 saiu 25 km "descarga"; com o código novo o mesmo estado dá 31
km). Refazer deixa o atleta com o plano que o coach geraria hoje.

Por que NÃO basta `ensure_plan(force=True)`: o contexto da IA traz o plano guardado da MESMA semana
("ESTA SEMANA É DE DESCARGA…") e a mensagem já enviada — e o modelo repete a própria resposta
(teste de 08/11: voltou os mesmos 25 km). Aqui o estado de ANTES do plano é reconstituído SÓ EM
MEMÓRIA durante a geração e desfeito logo depois.

Passos (com --apply):
  1) backup do plano e do histórico em ~/rollback_points/regerar-<atleta>-<semana>-<hora>/
  2) esconde (memória) o plano da semana e as mensagens do coach sobre ele
  3) gera pela IA (UMA chamada paga, ~R$0,40) via AIPlanService.ensure_plan(force=True) — que salva
     (a versão substituída vai pro arquivo permanente de versões)
  4) desfaz o esconde; se a IA falhou e caiu no plano de rede, RESTAURA o backup e aborta
  5) formata a mensagem da semana, ressincroniza o relógio (quem já empurrou antes) e ENVIA
     (CoachOutbox, kind weekly_plan)
Sem --apply: só mostra o que faria — SEM IA e SEM enviar.

    cd ~/runmind/backend && .venv/bin/python /tmp/regerar_semana.py --profile renato2 [--apply]
    [--week AAAA-MM-DD] [--no-send]   (normalmente via ops/regerar_semana.sh)
"""

import argparse
import asyncio
import io
import shutil
import sys
from contextlib import contextmanager, redirect_stdout
from datetime import date, datetime
from pathlib import Path

BACKEND = Path.home() / "runmind" / "backend"

sys.path.insert(0, str(BACKEND))

NOTICE = (
    "🔄 Refiz o plano desta semana com um ajuste na forma como leio os seus sinais de "
    "recuperação — este substitui o que te mandei antes."
)


class _Tee(io.TextIOBase):
    """Mostra a saída e guarda uma cópia (pra detectar o plano de rede da IA que falhou)."""

    def __init__(self, real):

        self.real = real

        self.copy = io.StringIO()

    def write(self, text):

        self.real.write(text)

        self.copy.write(text)

        return len(text)

    def flush(self):

        self.real.flush()


@contextmanager
def _week_hidden(profile: str, week: date):
    """O que o coach via ANTES de gerar o plano de `week` (só em memória; sempre desfeito)."""

    from app.infrastructure.persistence.coach_outbox_repository import CoachOutboxRepository
    from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository

    repo = WeeklyPlanRepository()

    stored = repo.load(profile)

    earlier = [p for p in repo.history(profile) if p.week_start < week]

    previous = earlier[-1] if earlier else None

    cutoff = datetime.fromisoformat(stored.generated_at) if stored and stored.generated_at else None

    original_load = WeeklyPlanRepository.load

    original_history = WeeklyPlanRepository.history

    original_recent = CoachOutboxRepository.recent

    def load(self, p):

        return previous if p == profile else original_load(self, p)

    def history(self, p):

        entries = original_history(self, p)

        return [x for x in entries if x.week_start < week] if p == profile else entries

    def recent(self, p, limit=3):

        entries = original_recent(self, p, 500)

        if p == profile and cutoff is not None:

            entries = [
                e for e in entries
                if datetime.fromisoformat(str(e.get("timestamp"))) < cutoff
            ]

        return entries[-limit:]

    WeeklyPlanRepository.load = load

    WeeklyPlanRepository.history = history

    CoachOutboxRepository.recent = recent

    try:

        yield

    finally:

        WeeklyPlanRepository.load = original_load

        WeeklyPlanRepository.history = original_history

        CoachOutboxRepository.recent = original_recent


def _backup(profile: str, week: date) -> Path:

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    dest = Path.home() / "rollback_points" / f"regerar-{profile}-{week:%Y%m%d}-{stamp}"

    dest.mkdir(parents=True, exist_ok=True)

    plans = BACKEND / "storage" / "plans"

    for src, label in (
        (plans / f"{profile}.json", "plano"),
        (plans / "history" / f"{profile}.json", "historico"),
    ):

        if src.exists():

            shutil.copy2(src, dest / f"{label}_{profile}.json")

    return dest


def _restore(dest: Path, profile: str) -> None:

    plans = BACKEND / "storage" / "plans"

    for label, target in (
        ("plano", plans / f"{profile}.json"),
        ("historico", plans / "history" / f"{profile}.json"),
    ):

        saved = dest / f"{label}_{profile}.json"

        if saved.exists():

            shutil.copy2(saved, target)


def _summary(plan) -> str:

    lines = [
        f"semana {plan.week_start:%d/%m} · fase {plan.phase} · ~{plan.weekly_volume} km"
        f"{' · DESCARGA' if plan.is_deload else ''}",
        f"objetivo: {plan.weekly_objective}",
    ]

    for s in plan.sessions:

        km = s.planned_distance_km or s.estimated_distance_km

        lines.append(f"  {s.day}: {s.workout_type} · {km if km else '-'} km")

    return "\n".join(lines)


async def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument("--profile", required=True)

    parser.add_argument("--week", help="segunda-feira AAAA-MM-DD (padrão: a PRÓXIMA semana)")

    parser.add_argument("--apply", action="store_true")

    parser.add_argument("--no-send", action="store_true", help="gera e salva, mas não envia")

    args = parser.parse_args()

    from app.application.assessment.training_assessment_builder import TrainingAssessmentBuilder
    from app.application.coach.planning.ai_plan_service import AIPlanService
    from app.application.garmin.plan_watch_sync import resync_watch_if_pushed
    from app.application.history.metrics_resolver import MetricsResolver
    from app.application.notifications.coach_outbox import CoachOutbox
    from app.application.planner.weekly_plan_message_formatter import WeeklyPlanMessageFormatter
    from app.application.planner.weekly_plan_service import WeeklyPlanService
    from app.application.use_cases.build_training_goal import BuildTrainingGoal
    from app.application.use_cases.load_runner_profile import LoadRunnerProfile
    from app.application.use_cases.load_training_history import LoadTrainingHistory
    from app.core.clock import use_athlete_timezone
    from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository

    profile = args.profile

    runner = LoadRunnerProfile.execute(profile)

    use_athlete_timezone(runner.timezone)

    week = date.fromisoformat(args.week) if args.week else WeeklyPlanService.upcoming_week_start()

    stored = WeeklyPlanRepository().load(profile)

    if stored is None or stored.week_start != week:

        print(
            f"ABORTADO: o plano guardado de '{profile}' não é da semana {week:%d/%m} "
            f"({'nenhum' if stored is None else f'{stored.week_start:%d/%m}'}). Nada foi feito."
        )

        return 1

    print(f"== PLANO GUARDADO AGORA ({profile}) ==\n{_summary(stored)}\n")

    if not args.apply:

        print(
            "DRY-RUN (sem IA, sem enviar). Com --apply: backup → gera pela IA (1 chamada paga) "
            "→ salva → ressincroniza o relógio → envia a mensagem."
        )

        return 0

    backup = _backup(profile, week)

    print(f"backup do plano e do histórico: {backup}")

    history = await LoadTrainingHistory.execute(profile=profile)

    assessment = TrainingAssessmentBuilder.build(runner, history)

    metrics = MetricsResolver.resolve(runner, history)

    goal = BuildTrainingGoal.execute(runner)

    tee = _Tee(sys.stdout)

    with _week_hidden(profile, week), redirect_stdout(tee):

        await AIPlanService.ensure_plan(
            profile=profile, runner=runner, assessment=assessment, metrics=metrics,
            goal=goal, history=history, reference_date=week, force=True,
        )

    if "IA falhou no plano" in tee.copy.getvalue():

        _restore(backup, profile)

        print("ABORTADO: a IA falhou e caiu no plano de rede — plano anterior RESTAURADO, nada enviado.")

        return 2

    plan = WeeklyPlanRepository().load(profile)

    print(f"\n== PLANO NOVO (salvo) ==\n{_summary(plan)}\n")

    message = WeeklyPlanMessageFormatter.format(runner.name, plan, profile=profile)

    lines = message.split("\n")

    lines[2:2] = [NOTICE, ""]

    message = "\n".join(lines)

    if await resync_watch_if_pushed(profile, plan):

        message += "\n\n⌚ Já mandei os treinos desta semana pro seu relógio."

        print("relógio: semana ressincronizada")

    else:

        print("relógio: não havia o que ressincronizar (desconectado ou nunca empurrou)")

    if args.no_send:

        print("--no-send: mensagem NÃO enviada. Texto:\n\n" + message)

        return 0

    await CoachOutbox.send(runner, message, profile=profile, kind="weekly_plan")

    print("mensagem enviada ao atleta (kind weekly_plan).")

    return 0


if __name__ == "__main__":

    sys.exit(asyncio.run(main()))
