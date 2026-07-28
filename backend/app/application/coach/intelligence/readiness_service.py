"""Vigia de prontidão — orquestra a leitura viva do corpo numa conduta do dia.

MODO OBSERVAÇÃO: avalia o corpo à luz do treino de hoje, aplica a cadência de
ORIENTAÇÃO (fala no 1º dia de decisão do episódio de alerta e quando PIORA;
cala nas repetições) e GRAVA no diário o que o coach DIRIA — mas NÃO envia nada.
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
from app.domain.entities.readiness_verdict import (
    READINESS_BRAKE,
    READINESS_CAUTION,
    ReadinessVerdict,
)
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

        history = repo.load(profile)

        previous = history[-1] if history else None

        # cadência de ORIENTAÇÃO (o coach orienta, não repete): fala no 1º dia
        # de decisão do episódio de alerta e quando PIORA; cala nas repetições.
        would_notify = (
            verdict.should_speak
            and ReadinessService._is_new_orientation(history, verdict)
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

    # tiers de ALERTA e sua severidade — o episódio é a sequência CONTÍGUA
    # deles; "piorar" é subir de severidade (CAUTION→BRAKE).
    _CONCERN_SEVERITY = {READINESS_CAUTION: 1, READINESS_BRAKE: 2}

    @staticmethod
    def _is_new_orientation(
        history: list[ReadinessDiaryEntry],
        verdict: ReadinessVerdict,
    ) -> bool:
        """Momento NOVO de orientar (o coach orienta, não repete):

        - ALERTA (CAUTION/BRAKE): fala no 1º dia de DECISÃO do episódio de
          alerta — mesmo sem virada de tier, o que corrige o dia puxado de
          quem está cronicamente no vermelho (a régua antiga, por virada de
          tier, calava justo aí) — E quando PIORA (CAUTION→BRAKE). Nas demais
          repetições, cala: o padrão de várias semanas no vermelho é
          orientação de OUTRO nível (resumo de domingo / cérebro), não ping
          diário.
        - VERDE/neutro: novidade = acabou de ENTRAR no estado (não repete).

        Ver [[feedback_orientar_nao_mandar]] e [[project_analise_corpo_garmin]].
        """

        severity = ReadinessService._CONCERN_SEVERITY.get(verdict.tier)

        if severity is None:

            # verde/neutro: só é novidade se mudou de tier (entrou agora)
            return not history or history[-1].tier != verdict.tier

        # varre o episódio de alerta contíguo (do mais recente pra trás): já
        # falamos nele? em que severidade no máximo? um dia SEM alerta encerra
        # o episódio (o próximo alerta é decisão nova).
        spoke_severity = 0

        for entry in reversed(history):

            if entry.tier not in ReadinessService._CONCERN_SEVERITY:

                break

            if entry.would_notify:

                spoke_severity = max(
                    spoke_severity,
                    ReadinessService._CONCERN_SEVERITY[entry.tier],
                )

        # 1º alerta do episódio (nunca falamos) OU piorou desde a última fala
        return spoke_severity == 0 or severity > spoke_severity

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
