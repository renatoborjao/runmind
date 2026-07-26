"""Vigia de prontidão — orquestra a leitura viva do corpo numa conduta do dia.

MODO OBSERVAÇÃO: avalia o corpo à luz do treino de hoje, faz o dedup por
MUDANÇA DE ESTADO e GRAVA no diário o que o coach DIRIA — mas NÃO envia nada.
É o gate do Renato: ler `/debug/readiness/{p}` dos atletas reais e conferir os
vereditos antes de ligar o envio de verdade (que vive no BodyConductNotifier).

Custo: zero de IA aqui — o veredito é determinístico (reusa o BodyReading já
computado). A mensagem ao atleta (Gemini) só entra quando o envio for ligado,
e só quando há alerta real. Ver [[project_analise_corpo_garmin]].
"""

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.intelligence.readiness_evaluator import (
    DEMAND_DEMANDING,
    DEMAND_EASY,
    DEMAND_REST,
    DEMAND_UNKNOWN,
    ReadinessEvaluator,
)
from app.application.coach.planning.body_conduct_engine import BodyConductEngine
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import now_local, today_local, use_athlete_timezone
from app.domain.entities.readiness_diary_entry import ReadinessDiaryEntry
from app.domain.entities.readiness_verdict import ReadinessVerdict
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.readiness_diary_repository import (
    ReadinessDiaryRepository,
)


class ReadinessService:

    @staticmethod
    async def evaluate(
        profile: str,
        persist: bool = True,
    ) -> tuple[ReadinessVerdict, ReadinessDiaryEntry]:

        runner = LoadRunnerProfile.execute(profile)

        # datas no fuso do atleta (o "hoje" que decide o treino do dia)
        use_athlete_timezone(runner.timezone)

        today = today_local()

        runner, plan = await CurrentPlanProvider.for_profile(profile)

        reading, _trajectory = BodyReadingService.read(profile, persist=False)

        demand = ReadinessService._todays_demand(plan, today)

        verdict = ReadinessEvaluator.evaluate(reading, demand)

        repo = ReadinessDiaryRepository()

        previous = repo.last(profile)

        # dedup por MUDANÇA DE ESTADO: só falaria quando o veredito VIRA — um
        # STRAINED que persiste 3 dias fala UMA vez (no dia que virou)
        would_notify = verdict.should_speak and (
            previous is None or previous.tier != verdict.tier
        )

        entry = ReadinessDiaryEntry(
            day=today.isoformat(),
            at=now_local().isoformat(),
            tier=verdict.tier,
            body_state=verdict.body_state,
            reason=verdict.reason,
            demand=demand,
            would_notify=would_notify,
            from_tier=previous.tier if previous else None,
        )

        if persist:

            repo.record(profile, entry)

        return verdict, entry

    @staticmethod
    def _todays_demand(plan: TrainingPlan, today) -> str:
        """Exigência do treino de HOJE — fonte única de 'exigente' via
        BodyConductEngine. Sem plano casável → UNKNOWN; sem sessão hoje → REST."""

        if not plan.sessions:

            return DEMAND_UNKNOWN

        for session in plan.sessions:

            if plan.session_date(session) == today:

                return (
                    DEMAND_DEMANDING
                    if BodyConductEngine.is_demanding(session)
                    else DEMAND_EASY
                )

        return DEMAND_REST
