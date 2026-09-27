"""BANCO DE CENÁRIOS DO COACH — roda na VM, contra os dados REAIS, sem gravar
plano, sem mandar mensagem, sem executar ação.

Pra que serve: toda mudança no coach passa por aqui ANTES do deploy (e o
resultado é lido por gente). Sem guardião no código, a segurança é esta: ver o
que a IA decide/fala de verdade, atleta por atleta, antes de ir pro ar.

Como roda (normalmente via ops/coach_lab.sh):
    .venv/bin/python /tmp/coach_lab.py [--overlay DIR] [--profiles a,b]
                                       [--only dossier,chat,analysis,...]

--overlay DIR: arquivos de app/ NOVOS (a versão candidata) — carregados em
memória no lugar dos de produção, mas com __file__ apontando pro caminho de
produção (o storage continua sendo o real). Sem overlay = o código no ar (o
"antes", pra comparar).

Cenários por atleta:
  dossier   o dossiê inteiro (o que TODA voz do coach lê)
  chat      o cérebro do chat decidindo 4 mensagens-padrão (sem executar)
  analysis  a análise do último treino
  conduct   o bom dia/véspera (só se o corpo pede recuperação e há treino puxado)
  missed    o juiz do furo sobre o último treino não feito da semana
  review    a leitura da semana (revisão semanal)
  plan      o plano da PRÓXIMA semana (modelo do plano, como no domingo)
"""

import argparse
import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import time
import traceback
from pathlib import Path

BACKEND = Path.home() / "runmind" / "backend"

CHAT_SCENARIOS = (
    "como eu tô evoluindo rumo ao meu objetivo?",
    "posso aumentar o volume essa semana?",
    "o último treino foi pesado demais, perna morta no fim",
    "monta um treino pra amanhã",
)

ALL = ("dossier", "chat", "analysis", "conduct", "missed", "review", "plan")


class _Overlay(importlib.abc.MetaPathFinder):
    """Carrega de DIR os módulos app.* que existirem lá, com __file__ de
    produção (o storage relativo ao __file__ segue sendo o real)."""

    def __init__(self, root: Path):

        self.root = root

    def find_spec(self, fullname, path=None, target=None):

        if fullname != "app" and not fullname.startswith("app."):

            return None

        rel = Path(*fullname.split("."))

        for candidate, is_pkg in (
            (rel.with_suffix(".py"), False),
            (rel / "__init__.py", True),
        ):

            source = self.root / candidate

            if source.exists():

                real = BACKEND / candidate

                return importlib.util.spec_from_file_location(
                    fullname,
                    str(real),
                    loader=importlib.machinery.SourceFileLoader(
                        fullname, str(source),
                    ),
                    submodule_search_locations=(
                        [str(real.parent)] if is_pkg else None
                    ),
                )

        return None


def _h(title: str) -> None:

    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}", flush=True)


def _s(title: str) -> None:

    print(f"\n--- {title} ---", flush=True)


async def _dossier(profile):

    from app.application.coach.context.athlete_dossier import AthleteDossier

    started = time.time()

    text = AthleteDossier.render(profile)

    _s(f"DOSSIÊ ({len(text)} chars, {time.time() - started:.1f}s)")

    print(text)


async def _chat(profile, runner, messages=CHAT_SCENARIOS):

    from app.application.coach.conversation.coach_brain import CoachBrain
    from app.application.coach.conversation.conversation_context_builder import (
        ConversationContextBuilder,
    )

    for message in messages:

        started = time.time()

        context = await ConversationContextBuilder.build(profile, message)

        decision = await CoachBrain.decide(
            runner_name=runner.name,
            context_facts=context,
            incoming_text=message,
        )

        _s(
            f"CHAT: \"{message}\" (contexto {len(context)} chars, "
            f"{time.time() - started:.1f}s)"
        )

        if decision is None:

            print("(cérebro falhou → cascata determinística)")

            continue

        print(f"say: {decision.say}")

        if decision.answer_card:

            print(f"cartão: {decision.answer_card}")

        for action in decision.all_actions:

            print(
                f"ação: {action.type} / {action.scope} / {action.target_day} — "
                f"{action.instruction}"
                + (f" | relação={action.relationship}" if action.relationship else "")
                + (f" | {action.distance_km:g} km" if action.distance_km else "")
                + (f" | alvo {action.target_time}" if action.target_time else "")
                + (f" | prova {action.race_date}" if action.race_date else "")
                + (f" | dias={action.days}" if action.days else "")
            )

        if decision.perception:

            print(f"percepção: {decision.perception}")


async def _analysis(profile):

    from app.application.coach.writer.ai_analysis_writer import AIAnalysisWriter
    from app.application.orchestrators.coach_analysis_builder import (
        CoachAnalysisBuilder,
    )

    result = await CoachAnalysisBuilder.build(profile)

    context = result["context"]

    activity = context.executed.activity

    analysis = await AIAnalysisWriter.write(context)

    _s(
        f"ANÁLISE do último treino ({activity.name}, "
        f"{activity.distance / 1000:.1f} km, {activity.start_date:%d/%m})"
    )

    if analysis is None:

        print("(IA falhou → texto determinístico)")

        return

    print(f"abertura: {analysis.headline}")

    for line in analysis.analysis:

        print(f"• {line}")

    print(f"atenção: {analysis.attention}")

    print(f"próximo passo: {analysis.next_step}")


async def _conduct(profile, runner):

    from app.application.coach.intelligence.body_reading_service import (
        BodyReadingService,
    )
    from app.application.coach.planning.body_conduct_engine import (
        BodyConductEngine,
    )
    from app.core.clock import today_local
    from app.infrastructure.persistence.weekly_plan_repository import (
        WeeklyPlanRepository,
    )

    reading, _ = BodyReadingService.read(profile, persist=False)

    plan = WeeklyPlanRepository().load(profile)

    today = today_local()

    session = (
        BodyConductEngine.next_demanding_session(plan, today)
        if plan is not None
        else None
    )

    _s(f"BOM DIA / VÉSPERA (corpo {reading.body_state})")

    if reading.body_state not in ("STRAINED", "RECOVERY_FLAG") or session is None:

        print("(não dispara: corpo sem alerta ou sem treino puxado à frente)")

        return

    decision = await BodyConductEngine.decide(
        runner, plan, reading, session, today, runner.goal, when="eve",
    )

    if decision is None:

        print("(IA falhou)")

        return

    print(f"conduta: {decision.action} | {decision.operations}")

    print(f"mensagem: {decision.message}")


async def _missed(profile, runner):
    """O juiz do furo sobre a última sessão da semana que passou sem ser
    feita (se houver)."""

    from app.application.coach.planning.missed_workout_judge import (
        MissedWorkoutJudge,
    )
    from app.application.planner.missed_workout_flow import MissedWorkoutFlow
    from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
    from app.application.use_cases.load_training_history import (
        LoadTrainingHistory,
    )
    from app.core.clock import today_local
    from app.infrastructure.persistence.weekly_plan_repository import (
        WeeklyPlanRepository,
    )

    plan = WeeklyPlanRepository().load(profile)

    history = await LoadTrainingHistory.execute(profile=profile)

    if plan is None or not plan.sessions:

        return

    today = today_local()

    fulfilled = WeeklyPlanMatcher.fulfilled_days(plan, history.activities)

    running = [s for s in plan.sessions if s.kind in ("run", "walk", "run_walk")]

    missed = [
        s for s in running
        if plan.session_date(s) < today and s.day not in fulfilled
    ]

    _s("FURO (juiz do treino não feito)")

    if not missed:

        print("(nenhum furo na semana)")

        return

    last = max(missed, key=plan.session_date)

    judgment = await MissedWorkoutJudge.judge(
        runner=runner,
        plan=plan,
        missed=last,
        done=len([s for s in running if s.day in fulfilled]),
        total=len(running),
        portrait=MissedWorkoutFlow._portrait(runner, history, plan),
    )

    print(f"furo: {last.day} {last.workout_type}")

    if judgment is None:

        print("(IA falhou)")

        return

    print(f"mensagem: {judgment.message}")

    print(f"proposta: {judgment.operations}")


async def _review(profile, runner):

    from app.application.review.weekly_review_builder import WeeklyReviewBuilder
    from app.application.review.weekly_review_narrative_writer import (
        WeeklyReviewNarrativeWriter,
    )
    from app.application.review.weekly_review_notifier import HISTORY_LIMIT
    from app.application.use_cases.load_training_history import (
        LoadTrainingHistory,
    )

    history = await LoadTrainingHistory.execute(
        profile=profile, limit=HISTORY_LIMIT,
    )

    review = WeeklyReviewBuilder.build(runner, history)

    narrative = await WeeklyReviewNarrativeWriter.write(
        runner.name, review, profile=profile,
    )

    _s("LEITURA DA SEMANA (revisão semanal)")

    for line in narrative or ["(IA falhou → fallback determinístico)"]:

        print(f"• {line}")


def _fmt_step(step, indent="    "):

    if step.steps:

        lines = [f"{indent}{step.reps}x:"]

        for child in step.steps:

            lines += _fmt_step(child, indent + "  ")

        return lines

    if step.distance_m:

        size = f"{step.distance_m:.0f}m"

    elif step.duration_sec:

        size = f"{step.duration_sec // 60}'{step.duration_sec % 60:02d}"

    else:

        size = "aberto"

    pace = f" {step.pace_min}-{step.pace_max}" if step.pace_min else ""

    hr = f" FC≤{step.hr_max}" if step.hr_max else ""

    return [f"{indent}{step.kind} {size}{pace}{hr}"]


async def _plan(profile, runner):

    from app.application.assessment.training_assessment_builder import (
        TrainingAssessmentBuilder,
    )
    from app.application.coach.planning.ai_plan_service import AIPlanService
    from app.application.history.metrics_resolver import MetricsResolver
    from app.application.planner.weekly_plan_service import WeeklyPlanService
    from app.application.use_cases.build_training_goal import BuildTrainingGoal
    from app.application.use_cases.load_training_history import (
        LoadTrainingHistory,
    )
    from app.core.config import get_settings
    from app.infrastructure.persistence.weekly_plan_repository import (
        WeeklyPlanRepository,
    )

    if runner.external_coach:

        _s("PLANO: treinador externo (não montamos)")

        return

    history = await LoadTrainingHistory.execute(profile=profile)

    assessment = TrainingAssessmentBuilder.build(runner, history)

    metrics = MetricsResolver.resolve(runner, history)

    goal = BuildTrainingGoal.execute(runner)

    week = WeeklyPlanService.upcoming_week_start()

    context = AIPlanService._build_context(
        profile, runner, metrics, goal, history, WeeklyPlanRepository(), week,
        assessment.run_walk,
    )

    started = time.time()

    plan = await AIPlanService._generate_ai(
        profile, runner.name, goal.name, week, context,
    )

    AIPlanService._fill_time_based_km(plan, metrics)

    model = (
        get_settings().plan_model
        if get_settings().plan_model_active_for(profile)
        else "flash"
    )

    _s(
        f"PLANO da semana {week:%d/%m} (contexto {len(context)} chars, {model}, "
        f"{time.time() - started:.0f}s) — fase {plan.phase}, "
        f"~{plan.weekly_volume:.1f} km"
    )

    if plan.weekly_objective:

        print(f"objetivo da semana: {plan.weekly_objective}")

    for session in plan.sessions:

        size = (
            f"{session.planned_distance_km:.1f} km"
            if session.planned_distance_km
            else f"{session.planned_duration_minutes} min"
            f" (~{session.estimated_distance_km or 0:.1f} km)"
        )

        print(f"  {session.day}: {session.workout_type} | {size}")

        print(f"    propósito: {session.purpose or session.objective}")

        for step in session.steps or []:

            print("\n".join(_fmt_step(step, "      ")))


async def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--overlay")

    parser.add_argument("--profiles", default="")

    parser.add_argument("--only", default=",".join(ALL))

    # mensagens próprias pro cenário de chat, separadas por "||"
    parser.add_argument("--messages", default="")

    args = parser.parse_args()

    sys.path.insert(0, str(BACKEND))

    if args.overlay:

        sys.meta_path.insert(0, _Overlay(Path(args.overlay)))

    from app.application.use_cases.load_runner_profile import LoadRunnerProfile
    from app.core.clock import use_athlete_timezone
    from app.infrastructure.persistence.runner_profile_repository import (
        RunnerProfileRepository,
    )

    profiles = [
        p for p in args.profiles.split(",") if p
    ] or RunnerProfileRepository().list_active()

    only = set(args.only.split(","))

    print(
        f"BANCO DE CENÁRIOS — código {'CANDIDATO (overlay)' if args.overlay else 'NO AR'}"
        f" — atletas: {', '.join(profiles)}"
    )

    for profile in profiles:

        _h(profile)

        try:

            runner = LoadRunnerProfile.execute(profile)

            use_athlete_timezone(runner.timezone)

        except Exception as e:

            print(f"(perfil falhou: {e})")

            continue

        steps = (
            ("dossier", lambda: _dossier(profile)),
            ("chat", lambda: _chat(
                profile, runner,
                [m.strip() for m in args.messages.split("||") if m.strip()]
                or CHAT_SCENARIOS,
            )),
            ("analysis", lambda: _analysis(profile)),
            ("conduct", lambda: _conduct(profile, runner)),
            ("missed", lambda: _missed(profile, runner)),
            ("review", lambda: _review(profile, runner)),
            ("plan", lambda: _plan(profile, runner)),
        )

        for name, run in steps:

            if name not in only:

                continue

            try:

                await run()

            except Exception:

                _s(f"{name.upper()} QUEBROU")

                traceback.print_exc(limit=6, file=sys.stdout)


if __name__ == "__main__":

    asyncio.run(main())
