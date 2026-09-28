from datetime import date

from app.application.coach.planning.coach_plan_engine import CoachPlanEngine
from app.application.coach.planning.executed_week_summary import (
    ExecutedWeekSummary,
)
from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from app.application.planner.engines.phase_engine import PhaseEngine
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.core.clock import today_local
from app.core.config import get_settings
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class AIPlanService:
    """Gera o plano da semana pela IA-treinadora a partir do retrato real
    do atleta. Cache por semana; treinador externo e run/walk seguem o
    caminho determinístico; se a IA falhar, cai no determinístico."""

    @staticmethod
    async def ensure_plan(
        profile: str,
        runner: RunnerProfile,
        assessment: TrainingAssessment,
        metrics: RunnerMetrics,
        goal: TrainingGoal,
        history: TrainingHistory,
        reference_date: date | None = None,
        force: bool = False,
        request: str = "",
    ) -> TrainingPlan:

        reference_date = reference_date or today_local()

        week_start = WeeklyPlanService.active_week_start(reference_date)

        repository = WeeklyPlanRepository()

        existing = repository.load(profile)

        # já há plano desta semana ATIVA (ou de uma futura já entregue):
        # reaproveita. force=True (o atleta pediu uma mudança) regenera pela
        # IA — mantendo o plano RICO, nunca caindo pro determinístico como
        # plano principal. O `>=` evita que uma leitura de domingo à tarde
        # regenere a semana atual por cima do plano da próxima já entregue.
        if (
            not force
            and existing is not None
            and existing.week_start >= week_start
        ):

            return existing

        # só treinador externo fica fora da IA (Ritmind só acompanha o
        # plano dele). Iniciante run/walk TAMBÉM é gerado pela IA, com os
        # dados do onboarding (peso/altura/capacidade) no contexto.
        if runner.external_coach:

            return AIPlanService._deterministic(
                profile, runner, assessment, metrics, goal,
                history, reference_date,
            )

        try:

            context = AIPlanService._build_context(
                profile, runner, metrics, goal, history,
                repository, week_start, assessment.run_walk,
                request=request,
            )

            # medidor: rotula a geração como "plano" (context manager reseta
            # depois, pra não vazar o rótulo quando o plano é gerado DENTRO de
            # um chat/briefing). Ver [[project_consumo_tokens]].
            from app.application.monitoring.token_meter import TokenMeter

            with TokenMeter.scope(profile, "plan"):

                plan = await AIPlanService._generate_ai(
                    profile, runner.name, goal.name, week_start, context,
                )

            # A periodização é decisão do COACH (ele vê a prova/distância no
            # retrato e marca a fase coerente com o plano que montou). Só caímos
            # no PhaseEngine determinístico se ele NÃO marcou (phase="IA") — aí é
            # rede, não regra. Ver [[feedback_tudo_dinamico]].
            if plan.phase == "IA":

                plan.phase = PhaseEngine.execute(goal, week_start)

            # REFAZER NO MEIO DA SEMANA (o atleta mudou meta/dias e pediu o
            # plano novo): o que já passou — e o de hoje, se já foi feito — fica
            # como estava. O feito é histórico, não se reescreve; a IA refaz só
            # o que falta.
            if existing is not None and existing.week_start == week_start:

                AIPlanService._keep_past_days(existing, plan, history)

                # o bloco que ESTA semana abriu continua valendo se a IA não
                # o redefiniu ao refazer
                if plan.block is None and existing.block is not None:

                    plan.block = existing.block

            AIPlanService._stamp_block(repository, profile, plan)

            # km estimado das sessões por TEMPO (duração ÷ pace) + volume real
            # da semana contando TODOS os tipos (não só os por distância).
            AIPlanService._fill_time_based_km(plan, metrics)

            repository.save(profile, plan)

            return plan

        except Exception as e:

            # IA fora do ar / plano inválido: nunca deixa o atleta sem plano
            print(
                f"IA falhou no plano de '{profile}', "
                f"fallback determinístico: {e}"
            )

            return AIPlanService._deterministic(
                profile, runner, assessment, metrics, goal,
                history, reference_date,
            )

    @staticmethod
    def _keep_past_days(old: TrainingPlan, new: TrainingPlan, history) -> None:
        """Sessões de dias que já passaram (e a de hoje já cumprida) vêm do
        plano antigo; a IA só manda do que falta em diante."""

        from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher

        today = today_local()

        done = {
            day.lower()
            for day in WeeklyPlanMatcher.fulfilled_days(old, history.activities)
        }

        kept = [
            s for s in old.sessions
            if old.session_date(s) < today
            or (old.session_date(s) == today and s.day.lower() in done)
        ]

        kept_days = {s.day for s in kept}

        fresh = [
            s for s in new.sessions
            if new.session_date(s) >= today and s.day not in kept_days
        ]

        new.sessions = sorted(kept + fresh, key=new.session_date)

    @staticmethod
    async def _generate_ai(
        profile: str,
        runner_name: str,
        objective: str,
        week_start: date,
        context: str,
    ) -> TrainingPlan:
        """Gera o plano pela IA. Perfil no canário do modelo PRO usa o modelo
        forte (raciocínio pesado, 1×/semana); se ele cair/rate-limit, FAZ
        FALLBACK pro Flash antes de deixar o determinístico assumir — não deixa
        a qualidade despencar por uma falha do PRO. Ver [[project_consumo_tokens]]."""


        settings = get_settings()

        if not settings.plan_model_active_for(profile):

            # caminho padrão: Flash (modelo/thinking atuais do CoachPlanEngine)
            return await CoachPlanEngine.generate(
                runner_name=runner_name, objective=objective,
                week_start=week_start, context=context,
            )

        # canário PRO: tenta o modelo forte; na falha, cai pro Flash
        try:

            return await CoachPlanEngine.generate(
                runner_name=runner_name, objective=objective,
                week_start=week_start, context=context,
                model=settings.plan_model,
                thinking_budget=settings.plan_thinking_budget,
            )

        except Exception as e:

            print(
                f"Plano PRO ({settings.plan_model}) falhou p/ '{profile}', "
                f"fallback pro Flash: {e}"
            )

            return await CoachPlanEngine.generate(
                runner_name=runner_name, objective=objective,
                week_start=week_start, context=context,
            )

    @staticmethod
    def _build_context(
        profile, runner, metrics, goal, history,
        repository, week_start, run_walk, request: str = "",
    ) -> str:

        # "plano anterior" = o da SEMANA ANTERIOR (a que acabou), NÃO o da
        # semana que estamos gerando. Antes vinha o plano guardado (o da
        # semana-alvo, futura): o resumo do executado casava as sessões
        # futuras contra zero atividade -> "zerou a semana" -> plano
        # cauteloso demais (bug do Renato/Fernanda: "após uma semana zerada"
        # mesmo tendo treinado). Vem do histórico, semana < alvo.
        last_week_plan = AIPlanService._previous_week_plan(
            repository,
            profile,
            week_start,
        )

        # últimas semanas de plano — pra a IA VER os tipos recentes e variar
        recent_plans = AIPlanService._recent_plans(
            repository,
            profile,
            week_start,
        )

        # dias EXATOS até a prova a partir da semana-alvo — perto dela, "1 vs 2
        # semanas" (piso de //7) muda a decisão de taper. O coach decide a
        # periodização; damos o número certo.
        days_to_race = (
            (goal.race_date - week_start).days
            if goal.race_date and goal.race_date > week_start
            else None
        )

        executed = ExecutedWeekSummary.build(
            last_week_plan,
            history.activities,
        )

        # o DOSSIÊ: meta, capacidade, evolução, corpo, percepção, padrões,
        # estímulos, plano vigente e o que o coach já sabe/disse — a MESMA base
        # do chat, da análise e das mensagens do dia (um coach, um cérebro).
        # Antes o plano montava o próprio recorte com 8 diretrizes separadas e
        # divergia do resto (varredura 26/09).
        from app.application.coach.context.athlete_dossier import AthleteDossier

        dossier = AthleteDossier.render(
            profile, runner=runner, history=history,
        )

        return PlanContextBuilder.build(
            runner=runner,
            goal=goal,
            week_start=week_start,
            today=today_local(),
            days_to_race=days_to_race,
            run_walk=run_walk,
            last_plan=last_week_plan,
            recent_plans=recent_plans,
            executed=executed,
            dossier=dossier,
            block=AIPlanService._block_line(
                AIPlanService._active_block(repository, profile, week_start),
            ),
            request=request,
        )

    @staticmethod
    def _active_block(repository, profile, week_start: date):
        """(bloco, semana k) em andamento na semana-alvo — o último plano
        ANTERIOR que abriu/redefiniu um bloco que ainda cobre a semana. None se
        não há (esta semana abre um). Best-effort: falha = sem bloco."""

        try:

            return AIPlanService._find_block(repository, profile, week_start)

        except Exception as e:

            print(f"Bloco ativo falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    def _find_block(repository, profile, week_start: date):

        past = sorted(
            (p for p in repository.history(profile) if p.week_start < week_start),
            key=lambda p: p.week_start,
            reverse=True,
        )

        current = repository.load(profile)

        if current is not None and current.week_start < week_start:

            past.insert(0, current)

        for plan in past:

            block = plan.block

            if not block:

                continue

            try:

                start = date.fromisoformat(block["start"])

                weeks = int(block["weeks"])

            except (KeyError, TypeError, ValueError):

                return None

            index = (week_start - start).days // 7 + 1

            return (block, index) if 1 <= index <= weeks else None

        return None

    @staticmethod
    def _block_line(active) -> str:

        if active is None:

            return (
                "BLOCO: nenhum em andamento — esta semana ABRE um bloco novo: "
                "defina \"block\" (foco rumo à meta/prova e o papel de cada "
                "semana)."
            )

        block, index = active

        roles = " | ".join(block["weeks_plan"])

        role = block["weeks_plan"][index - 1]

        return (
            f"BLOCO EM ANDAMENTO — semana {index} de {block['weeks']} (desde "
            f"{date.fromisoformat(block['start']):%d/%m}), foco: {block['focus']}. "
            f"Plano do bloco: {roles}. ESTA semana: {role}. Monte cumprindo "
            "esse papel; se precisar desviar, redefina \"block\"."
        )

    @staticmethod
    def _stamp_block(repository, profile, plan: TrainingPlan) -> None:
        """Carimba o bloco no plano: o que a IA abriu/redefiniu começa ESTA
        semana; senão segue o bloco em andamento. `block_label` pro atleta ver
        o arco. Best-effort — nunca derruba o plano."""

        try:

            if plan.block:

                plan.block = {**plan.block, "start": plan.week_start.isoformat()}

                block, index = plan.block, 1

            else:

                active = AIPlanService._active_block(
                    repository, profile, plan.week_start,
                )

                if active is None:

                    plan.block_label = None

                    return

                block, index = active

            plan.block_label = (
                f"semana {index} de {block['weeks']} — {block['focus']}"
            )

        except Exception as e:

            print(f"Bloco do plano falhou p/ '{profile}': {e}")

    @staticmethod
    def _weeks_since_race(profile, history, week_start: date) -> int | None:
        """Semanas desde a última PROVA (do ponto de vista da semana que estamos
        gerando). Fonte principal: o RESULTADO que o coach já registrou (debrief
        da prova-alvo — o que o sistema já SABIA); rede: atividades marcadas como
        prova. None sem prova recente. Best-effort — falhar nunca derruba o
        plano. Ver [[race_detector]]."""

        try:

            from app.application.history.race_detector import RaceDetector
            from app.infrastructure.persistence.race_result_repository import (
                RaceResultRepository,
            )

            past_results = RaceResultRepository().load(profile)

            race = RaceDetector.most_recent(
                history.activities, week_start, past_results=past_results
            )

            return race.weeks_ago if race else None

        except Exception as e:  # noqa: BLE001

            print(f"Detecção de prova recente falhou: {e}")

            return None

    @staticmethod
    def _previous_week_plan(repository, profile, week_start):
        """Plano da SEMANA ANTERIOR mais recente (week_start < alvo), do
        histórico. É contra ele que se mede o executado — nunca contra o da
        semana-alvo (que ainda não aconteceu)."""

        past = [
            plan
            for plan in repository.history(profile)
            if plan.week_start < week_start
        ]

        if not past:

            return None

        return max(past, key=lambda plan: plan.week_start)

    @staticmethod
    def _recent_plans(repository, profile, week_start, limit: int = 4):
        """As últimas `limit` semanas de plano (week_start < alvo), em ordem
        cronológica. A IA lê os TIPOS recentes pra VARIAR o estímulo em vez de
        repetir o mesmo trio semana após semana."""

        past = sorted(
            (
                plan
                for plan in repository.history(profile)
                if plan.week_start < week_start
            ),
            key=lambda plan: plan.week_start,
        )

        return past[-limit:]

    @staticmethod
    def _fill_time_based_km(plan, metrics) -> None:
        """Estima o km de cada sessão por TEMPO (duração ÷ pace) e recomputa o
        volume da semana com o km EFETIVO — pra o volume/meta contar TODOS os
        tipos, não só os por distância. Pace da sessão; se não houver, cai no
        pace fácil real do atleta. Best-effort: falhar aqui nunca quebra o plano."""

        from app.application.planner.pace_formatter import PaceFormatter

        easy_mid = None

        if metrics.easy_pace_min and metrics.easy_pace_max:

            easy_mid = (metrics.easy_pace_min + metrics.easy_pace_max) / 2

        for session in plan.sessions:

            if session.planned_distance_km or not session.planned_duration_minutes:

                continue

            paces = [
                p
                for p in (
                    PaceFormatter.to_minutes(session.target_pace_min),
                    PaceFormatter.to_minutes(session.target_pace_max),
                )
                if p
            ]

            pace_mid = sum(paces) / len(paces) if paces else easy_mid

            if pace_mid:

                session.estimated_distance_km = round(
                    session.planned_duration_minutes / pace_mid, 1
                )

        plan.weekly_volume = round(
            sum(s.effective_distance_km or 0 for s in plan.sessions), 1
        )

    @staticmethod
    def _weeks_to_race(goal: TrainingGoal, week_start: date) -> int | None:

        if goal.race_date is None or goal.race_date <= week_start:

            return None

        return (goal.race_date - week_start).days // 7

    @staticmethod
    def _deterministic(
        profile, runner, assessment, metrics, goal,
        history, reference_date,
    ) -> TrainingPlan:

        return WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            reference_date=reference_date,
            history=history,
        )
