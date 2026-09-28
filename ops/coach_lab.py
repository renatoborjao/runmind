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
import re
from datetime import timedelta
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

ALL = (
    "dossier", "chat", "analysis", "conduct", "missed", "review", "plan",
    "recap", "race", "reengage",
)


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


async def _replan(profile, runner, messages):
    """REFAZER A SEMANA pelo caminho real: cérebro → pedido que desce pro plano
    → IA refaz a semana ATUAL (nada é gravado). 2 chamadas por mensagem."""

    from app.application.coach.conversation.coach_brain import CoachBrain
    from app.application.coach.conversation.coach_brain_executor import (
        CoachBrainExecutor,
    )
    from app.application.coach.conversation.conversation_context_builder import (
        ConversationContextBuilder,
    )
    from app.application.planner.current_plan_provider import CurrentPlanProvider
    from app.core.clock import today_local

    for message in messages:

        context = await ConversationContextBuilder.build(profile, message)

        decision = await CoachBrain.decide(
            runner_name=runner.name, context_facts=context, incoming_text=message,
        )

        actions = decision.all_actions if decision else []

        request = CoachBrainExecutor._replan_request(message, actions)

        _s(f"REFAZER: \"{message}\" — ações {[a.type for a in actions]}")

        print(f"pedido que desce pro plano: {request}")

        # uma geração só (custa crédito pago — 28/09): o "sem pedido" é o antes
        for label, req in (("COM o pedido", request),):

            _, plan = await CurrentPlanProvider.for_profile(
                profile, force=True, request=req,
            )

            print(f"\n[{label}] objetivo: {plan.weekly_objective}")

            for session in plan.sessions:

                day = plan.session_date(session)

                if day < today_local():

                    continue

                size = (
                    f"{session.planned_distance_km:g} km"
                    if session.planned_distance_km
                    else f"{session.planned_duration_minutes or 0:g} min"
                )

                print(
                    f"  {day:%a %d/%m} {session.workout_type} · {size} · "
                    f"{session.target_pace_min}-{session.target_pace_max}"
                )

                print(f"     {(session.structure or '').replace(chr(10), ' / ')[:240]}")


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

    if reading.body_state not in ("STRAINED", "RECOVERY_FLAG"):

        print("(não dispara: corpo sem alerta)")

        return

    if session is None:

        # semana vigente sem treino puxado à frente: usa o plano da PRÓXIMA
        # semana (gerado em memória, sem gravar) e a véspera do 1º puxado dela
        plan = await _next_week_plan(profile, runner)

        session = next(
            (s for s in plan.sessions if BodyConductEngine.is_demanding(s)),
            None,
        )

        if session is None:

            print("(sem treino puxado na próxima semana)")

            return

        from datetime import timedelta

        today = plan.session_date(session) - timedelta(days=1)

        print(f"(simulando a véspera de {session.day} {session.workout_type})")

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


async def _next_week_plan(profile, runner):
    """Plano da próxima semana em memória (mesmo caminho do domingo, sem
    gravar)."""

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
    from app.infrastructure.persistence.weekly_plan_repository import (
        WeeklyPlanRepository,
    )

    history = await LoadTrainingHistory.execute(profile=profile)

    metrics = MetricsResolver.resolve(runner, history)

    goal = BuildTrainingGoal.execute(runner)

    week = WeeklyPlanService.upcoming_week_start()

    context = AIPlanService._build_context(
        profile, runner, metrics, goal, history, WeeklyPlanRepository(), week,
        TrainingAssessmentBuilder.build(runner, history).run_walk,
    )

    return await AIPlanService._generate_ai(
        profile, runner.name, goal.name, week, context,
    )


async def _recap(profile, runner):
    """Recap do MÊS PASSADO (o que sai no dia 1º)."""

    from datetime import date

    from app.application.review.monthly_recap_builder import MonthlyRecapBuilder
    from app.application.review.monthly_recap_narrative_writer import (
        MonthlyRecapNarrativeWriter,
    )
    from app.application.review.monthly_recap_notifier import HISTORY_LIMIT
    from app.application.use_cases.load_training_history import (
        LoadTrainingHistory,
    )
    from app.core.clock import today_local

    today = today_local()

    month_start = (date(today.year, today.month, 1) - timedelta(days=1)).replace(day=1)

    history = await LoadTrainingHistory.execute(profile=profile, limit=HISTORY_LIMIT)

    recap = MonthlyRecapBuilder.build(runner, history, month_start)

    _s(f"RECAP MENSAL ({month_start:%m/%Y})")

    if recap is None:

        print("(sem dados no mês)")

        return

    for line in await MonthlyRecapNarrativeWriter.write(
        runner.name, recap, profile=profile,
    ) or ["(IA falhou)"]:

        print(f"• {line}")


async def _race(profile, runner):
    """Narrativa do debrief da prova mais recente (só o narrador — o debrief
    real aposenta a prova no perfil, aqui nada é gravado)."""

    from datetime import date

    from app.application.coach.writer.race_narrative_writer import (
        RaceNarrativeWriter,
    )
    from app.application.history.race_detector import RaceDetector
    from app.application.orchestrators.coach_analysis_builder import (
        CoachAnalysisBuilder,
    )
    from app.domain.entities.training_goal import TrainingGoal
    from app.infrastructure.persistence.activity_archive_repository import (
        ActivityArchiveRepository,
    )
    from app.infrastructure.persistence.race_repository import RaceRepository

    races = [
        a for a in ActivityArchiveRepository().load_activities(profile)
        if RaceDetector._is_race(a)
    ]

    _s("DEBRIEF DE PROVA (narrador)")

    if not races:

        print("(nenhuma prova no histórico)")

        return

    race = max(races, key=lambda a: a.start_date)

    registered = next(
        (
            r for r in RaceRepository().load(profile)
            if r.get("date") == race.start_date.date().isoformat()
        ),
        {},
    )

    goal = TrainingGoal(
        name=runner.goal,
        distance_km=round(race.distance / 1000),
        target_time=registered.get("target_time"),
        race_date=date.fromisoformat(race.start_date.date().isoformat()),
    )

    enriched = (await CoachAnalysisBuilder.build(profile, activity=race))["enriched"]

    print(f"prova: {race.name} {race.start_date:%d/%m} {race.distance / 1000:.1f} km, alvo {goal.target_time}")

    print(await RaceNarrativeWriter.write(profile, runner, enriched, goal))


async def _reengage(profile, runner):
    """Mensagem de reaproximação (atleta sumido há ~12 dias, simulado)."""

    from app.application.coach.memory.runner_memory_service import (
        RunnerMemoryService,
    )
    from app.application.review.reengagement_writer import ReengagementWriter

    facts = ReengagementWriter.facts(
        runner.name, 12, "rodagem de 6 km há 12 dias", "vinha 3x/semana",
        runner.goal, RunnerMemoryService.motivation_anchor(profile) or None,
        profile,
    )

    _s("REENGAJAMENTO (simulado: 12 dias sumido)")

    print(await ReengagementWriter.write(profile, facts))


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

    block_ctx = next(
        (line for line in context.splitlines() if line.startswith("BLOCO")), "",
    )

    print(f"contexto do bloco: {block_ctx[:160]}")

    if plan.block:

        print(f"BLOCO ABERTO: {plan.block['focus']} | " + " | ".join(plan.block["weeks_plan"]))

    print(f"dia extra: {plan.extra_day_note or '—'}")

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


# AVALIAÇÃO DO CÉREBRO: o CATÁLOGO do que atleta real fala, com o GABARITO do
# que o coach deve DECIDIR (tipos de ação, relação da meta, dias, dia-alvo,
# escopo, cartão, percepção) + a FALA (sem promessa vazia, com acento). Os erros
# de 27/09 (pular a semana, relógio, "quando chega o plano") eram situações
# fora do gabarito — o catálogo cobre as categorias todas e roda antes de todo
# deploy do coach: `bash ops/coach_lab.sh <saida> --braineval 0 --repeats 1`.
# (perfil, mensagem, tipos esperados (conjuntos aceitos), extra)
NONE = [set()]

BRAIN_EVAL = [
    # ---- META / PROVA
    ("leonardo", "O objetivo agora é correr 10 km em 55 minutos. Tenho "
     "disponibilidade de terça, quinta e domingo",
     [{"goal", "days"}, {"goal", "days", "replan"}],
     {"relationship": ("replace", "primary"),
      "days": ["Tuesday", "Thursday", "Sunday"]}),
    ("renato2", "também quero correr a São Silvestre em 31/12, sem tempo, só "
     "pra curtir", [{"goal"}], {"relationship": ("additional",)}),
    ("renato2", "meu objetivo principal agora é fazer a meia em 1h50",
     [{"goal"}], {"relationship": ("primary",)}),
    ("renato2", "esquece a 15k, não vou mais correr ela, meu foco agora é só "
     "a meia", [{"goal"}], {"relationship": ("replace",)}),
    ("joaosoares", "vou correr uma prova de 5 km dia 25/10 pra testar, quero "
     "fazer em 24 minutos", [{"goal"}],
     {"relationship": ("stepping_stone", "additional")}),
    ("fernanda", "esquece perder peso, agora meu objetivo é correr 10 km em "
     "50 minutos", [{"goal"}], {"relationship": ("replace", "primary")}),
    # ---- DIAS
    ("joaosoares", "a partir de agora só consigo correr terça e sábado",
     [{"days"}, {"days", "replan"}], {"days": ["Tuesday", "Saturday"]}),
    ("helio", "agora consigo correr 4x: segunda, quarta, sexta e sábado",
     [{"days"}, {"days", "replan"}],
     {"days": ["Monday", "Wednesday", "Friday", "Saturday"]}),
    # ---- MUDAR A SEMANA
    ("fernanda", "troca o treino de terça pra quarta e o de sexta pra sábado",
     [{"move"}], {"count": 2}),
    ("mauricio", "o treino de terça pode ser mais leve? tô cansado",
     [{"adjust"}, {"simplify"}], {"target_day": "Tuesday"}),
    ("renato2", "passa o longão de sábado pra domingo", [{"move"}],
     {"target_day": "Sunday"}),
    ("renato2", "passa o treino de quinta pra sexta e deixa ele mais curto, "
     "uns 30 minutos", [{"move"}],
     {"target_day": "Friday", "content_change": True}),
    # adjust/simplify + replan juntos: o replan vence e leva o pedido junto
    # (28/09) — refaz a semana honrando o "só leve até sexta"
    ("mauricio", "tô gripado, refaz minha semana só com treino leve até "
     "sexta", [{"replan"}, {"adjust"}, {"simplify"}, {"adjust", "replan"},
               {"simplify", "replan"}], {}),
    ("fernanda", "refaz minha semana, mudou tudo aqui na minha rotina",
     [{"replan"}], {}),
    # ---- PULAR (aplica na hora)
    # "amanhã" é relativo ao dia em que o catálogo roda (fixo "Monday" só
    # valia no domingo em que foi escrito)
    ("helio", "amanhã não vou conseguir treinar, tenho plantão", [{"skip"}],
     {"target_day": "TOMORROW", "scope": "single_session"}),
    ("joaosoares", "estou resfriado, não vou conseguir treinar essa semana",
     [{"skip"}], {"scope": "week"}),
    ("leonardo", "vou viajar a trabalho a semana toda, não vou conseguir "
     "treinar", [{"skip"}], {"scope": "week"}),
    # ---- AVULSO
    ("fernanda", "monta um treino pra quarta", [{"one_off"}],
     {"target_day": "Wednesday"}),
    ("leonardo", "quero um treino pra quarta, vou ter tempo livre",
     [{"one_off"}], {"target_day": "Wednesday"}),
    # ---- ROTINA / PREFERÊNCIA DURÁVEL
    ("helio", "a partir da próxima semana quero treinos de no máximo 45 "
     "minutos durante a semana", [{"routine"}], {}),
    ("renato2", "de agora em diante quero o longão sempre sem pace, só por "
     "sensação", [{"routine"}, {"preference"}], {}),
    # com fartlek NA SEMANA, negociar a troca dele (perguntar ou ajustar) é o
    # comportamento desenhado (aversão: negocia, não obedece); o "não gosto"
    # durável vai pra memória pela extração. Sem fartlek na semana: routine.
    ("joaosoares", "não gosto de fartlek, prefiro tiro na pista",
     [{"preference"}, {"routine"}, {"adjust"}, {"routine", "adjust"}, set()], {}),
    # ---- RELÓGIO (manda na hora, nunca "vou tentar")
    ("renato2", "manda os treinos da semana pro relógio", [{"watch"}], {}),
    ("mauricio", "não chegou no Garmin, tenta de novo", [{"watch"}], {}),
    # ---- TÊNIS / TREINADOR
    ("fernanda", "comprei um tênis novo, um Adidas Adizero SL", [{"shoe"}], {}),
    ("mauricio", "quantos km tem meu Corre Turbo?", [{"shoe"}], {}),
    ("leonardo", "contratei uma assessoria, vou seguir o plano do meu "
     "treinador agora", [{"coach_switch"}], {}),
    # ---- PERGUNTA COM DADO EXATO (cartão)
    ("renato2", "qual o meu próximo treino?", NONE,
     {"card": ("next_training",)}),
    ("fernanda", "me manda meu plano da semana", NONE,
     {"card": ("weekly_plan",)}),
    ("mauricio", "quais são meus paces?", NONE, {"card": ("paces",)}),
    ("joaosoares", "como tá meu corpo hoje?", NONE, {"card": ("body",)}),
    ("renato2", "vou conseguir fazer a meia abaixo de 2h?", NONE,
     {"card": ("race",)}),
    ("leonardo", "como eu tô evoluindo?", NONE,
     {"card": ("fitness", "portrait")}),
    # ---- PERGUNTA SEM MUDANÇA (responde, não mexe)
    ("renato2", "o longão de sábado é 12 km né?", NONE, {}),
    ("mauricio", "meu longão é no sábado, certo?", NONE, {}),
    ("leonardo", "tá chovendo, como faço o treino de sexta na esteira?", NONE,
     {"card": (None,)}),
    ("helio", "quando chega meu plano novo?", NONE, {}),
    ("fernanda", "o que é bom comer antes do longão?", NONE, {}),
    ("mauricio", "posso fazer musculação no mesmo dia do treino?", NONE, {}),
    # ---- RELATO / PERCEPÇÃO / VIDA
    ("joaosoares", "o treino de sábado foi pesado, perna morta no fim", NONE,
     {"perception": True}),
    ("renato2", "o longão de sábado foi ok, uns 7 de 10 de esforço", NONE,
     {"perception": True}),
    ("mauricio", "tô sentindo uma dorzinha no joelho direito",
     [set(), {"adjust"}, {"simplify"}], {}),
    ("helio", "tô meio desanimado essa semana", NONE, {}),
    ("renato2", "tive uma recaída no vape, mas já parei faz 2 dias", NONE, {}),
    ("renato2", "acho que aguento mais, quero aumentar o volume essa semana",
     [set(), {"adjust"}], {}),
    # ---- CONVERSA
    ("helio", "valeu, coach!", NONE, {}),
    ("fernanda", "bom dia!", NONE, {}),
]


def _grade(decision, expected_sets, extra) -> list[str]:
    """Lista de erros (vazia = acertou): a DECISÃO (ações, meta, dias, dia,
    escopo, cartão, percepção) e a FALA (sem promessa vazia, com acento)."""

    if decision is None:

        return ["cérebro falhou"]

    from app.infrastructure.integrations.gemini.client import (
        unaccented_portuguese,
    )

    actions = decision.all_actions

    types = {a.type for a in actions}

    errors = []

    if types not in expected_sets:

        errors.append(f"ações {sorted(types)} ≠ {[sorted(e) for e in expected_sets]}")

    if "relationship" in extra:

        rel = next((a.relationship for a in actions if a.type == "goal"), None)

        if rel not in extra["relationship"]:

            errors.append(f"relação {rel} ≠ {extra['relationship']}")

    if "days" in extra:

        days = next((a.days for a in actions if a.type == "days"), None)

        if days != extra["days"]:

            errors.append(f"dias {days} ≠ {extra['days']}")

    if "target_day" in extra:

        target = next((a.target_day for a in actions), None)

        expected = extra["target_day"]

        if expected == "TOMORROW":

            from datetime import timedelta

            from app.core.clock import today_local

            expected = (
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday", "Sunday",
            )[(today_local() + timedelta(days=1)).weekday()]

        if target != expected:

            errors.append(f"dia-alvo {target} ≠ {expected}")

    if "scope" in extra:

        scope = next((a.scope for a in actions), None)

        if scope != extra["scope"]:

            errors.append(f"escopo {scope} ≠ {extra['scope']}")

    if extra.get("content_change") and not any(a.content_change for a in actions):

        errors.append("mudança de conteúdo não capturada")

    if "card" in extra and decision.answer_card not in extra["card"]:

        errors.append(f"cartão {decision.answer_card} ≠ {extra['card']}")

    if "count" in extra and len(actions) != extra["count"]:

        errors.append(f"{len(actions)} ações ≠ {extra['count']}")

    if extra.get("perception") and not decision.perception:

        errors.append("percepção não registrada")

    say = decision.say or ""

    if PROMISE_SAY.search(say) and not types:

        errors.append(f"promete sem ação: \"{say[:80]}\"")

    if unaccented_portuguese(say):

        errors.append("fala sem acento")

    return errors


# a mesma régua da auditoria semanal (ops/coach_audit.py)
PROMISE_SAY = re.compile(
    r"(estou preparando|tô preparando|em instantes|já te envio|vou te mandar|"
    r"vou te enviar|vou montar e te|estou montando|em breve te envio|"
    r"vou tentar|vou (sincronizar|cancelar|pausar|pular|tirar|remover|"
    r"atualizar|refazer|mandar|enviar))",
    re.I,
)


async def _brain_eval(budgets: list[int], repeats: int) -> None:

    from app.application.coach.conversation.coach_brain import CoachBrain
    from app.application.coach.conversation.conversation_context_builder import (
        ConversationContextBuilder,
    )
    from app.application.use_cases.load_runner_profile import LoadRunnerProfile
    from app.core.config import get_settings

    contexts = {}

    for profile, message, *_ in BRAIN_EVAL:

        contexts[(profile, message)] = await ConversationContextBuilder.build(
            profile, message,
        )

    summary = []

    for budget in budgets:

        get_settings().coach_brain_thinking_budget = budget

        _h(f"CÉREBRO com raciocínio {budget}")

        hits, total, seconds = 0, 0, []

        for profile, message, expected_sets, extra in BRAIN_EVAL:

            runner = LoadRunnerProfile.execute(profile)

            for _ in range(repeats):

                started = time.time()

                decision = await CoachBrain.decide(
                    runner_name=runner.name,
                    context_facts=contexts[(profile, message)],
                    incoming_text=message,
                )

                seconds.append(time.time() - started)

                errors = _grade(decision, expected_sets, extra)

                total += 1

                hits += not errors

                mark = "OK " if not errors else "ERR"

                print(f"{mark} {profile}: \"{message[:60]}\" {'; '.join(errors)}")

        seconds.sort()

        median = seconds[len(seconds) // 2]

        worst = seconds[-1]

        summary.append(
            f"raciocínio {budget}: {hits}/{total} certos | mediana {median:.1f}s "
            f"| pior {worst:.1f}s"
        )

    _h("RESUMO")

    print("\n".join(summary))


def _read_only() -> None:
    """O lab SÓ LÊ: toda escrita que um redator/motor faz de passagem vira
    no-op. Antes a revisão semanal simulada gravava a "cobrança da semana" no
    log de atenção de PRODUÇÃO (Hélio/João 27/09: cobrança fantasma no dossiê)."""

    import importlib

    for module, owner, method in (
        ("app.infrastructure.persistence.coach_attention_log",
         "CoachAttentionLog", "record"),
        ("app.infrastructure.persistence.weekly_plan_repository",
         "WeeklyPlanRepository", "save"),
        ("app.infrastructure.persistence.plan_proposal_repository",
         "PlanProposalRepository", "save"),
        ("app.infrastructure.persistence.missed_notification_repository",
         "MissedNotificationRepository", "mark"),
        ("app.infrastructure.persistence.runner_profile_repository",
         "RunnerProfileRepository", "update_fields"),
        ("app.infrastructure.persistence.dispatch_guard", "DispatchGuard", "mark"),
        ("app.application.coach.intelligence.perception_recorder",
         "PerceptionRecorder", "from_chat"),
    ):

        try:

            cls = getattr(importlib.import_module(module), owner)

            setattr(cls, method, staticmethod(lambda *a, **k: None))

        except Exception as e:  # noqa: BLE001

            print(f"(lab: não blindei {owner}.{method}: {e})")


async def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--overlay")

    parser.add_argument("--profiles", default="")

    parser.add_argument("--only", default=",".join(ALL))

    # mensagens próprias pro cenário de chat, separadas por "||"
    parser.add_argument("--messages", default="")

    # avaliação do cérebro com gabarito: orçamentos de raciocínio a comparar
    # (ex.: "0,4096") e repetições por frase
    parser.add_argument("--braineval", default="")

    parser.add_argument("--repeats", type=int, default=2)

    args = parser.parse_args()

    sys.path.insert(0, str(BACKEND))

    if args.overlay:

        sys.meta_path.insert(0, _Overlay(Path(args.overlay)))

    _read_only()

    from app.application.use_cases.load_runner_profile import LoadRunnerProfile
    from app.core.clock import use_athlete_timezone
    from app.infrastructure.persistence.runner_profile_repository import (
        RunnerProfileRepository,
    )

    if args.braineval:

        await _brain_eval(
            [int(b) for b in args.braineval.split(",") if b.strip()],
            args.repeats,
        )

        return

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
            ("recap", lambda: _recap(profile, runner)),
            ("race", lambda: _race(profile, runner)),
            ("reengage", lambda: _reengage(profile, runner)),
            # só quando pedido (--only replan): chama a IA 2x por mensagem
            ("replan", lambda: _replan(
                profile, runner,
                [m.strip() for m in args.messages.split("||") if m.strip()]
                or ["tô gripado, refaz minha semana só com treino leve até sexta"],
            )),
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
