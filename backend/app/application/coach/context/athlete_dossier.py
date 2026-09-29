"""DOSSIÊ DO ATLETA — o coach tem UM cérebro.

Antes, cada voz do coach (plano, chat, análise do treino, bom dia, furo, revisão
semanal, recap, leitura do corpo, debrief de prova, reengajamento) montava o
PRÓPRIO recorte do atleta. Resultado real (varredura 26/09): o chat sugeria 32 km
com o plano segurando em 30; o panorama semanal desmentia a "Forma"; a descarga
mandava cortar enquanto a leitura do corpo mandava manter. Cada voz sabia um
pedaço — e um pedaço diferente.

Aqui mora o quadro INTEIRO, montado de UMA fonte e renderizado igual pra todas as
vozes: quem ele é e o que busca, capacidade hoje, volume e evolução, corpo,
percepção, padrões/estímulos, plano da semana e o que o coach já sabe, disse e
decidiu. Cada voz só acrescenta a SUA tarefa por cima. Voz nova do coach = uma
linha: `AthleteDossier.render(profile)`.

Tudo aqui é FATO + CONHECIMENTO de treinador — nunca regra (quem decide é a IA,
[[feedback_ia_decide_sem_regras]]). Síncrono e só leitura (histórico do arquivo
permanente, nada de Strava/Garmin ao vivo). Best-effort por seção: o que falhar
não entra, o resto segue."""

from dataclasses import dataclass, field
from datetime import date, timedelta

# seções (nomes estáveis — as vozes excluem as que não servem à tarefa delas)
WHO = "who"
CAPACITY = "capacity"
EVOLUTION = "evolution"
BODY = "body"
PERCEPTION = "perception"
PATTERNS = "patterns"
PLAN_WEEK = "plan_week"
COACH_MIND = "coach_mind"

SECTIONS = (
    WHO, CAPACITY, EVOLUTION, BODY, PERCEPTION, PATTERNS, PLAN_WEEK, COACH_MIND,
)

_TITLES = {
    WHO: "QUEM É E O QUE BUSCA",
    CAPACITY: "CAPACIDADE HOJE",
    EVOLUTION: "VOLUME E EVOLUÇÃO",
    BODY: "CORPO (carga × recuperação)",
    PERCEPTION: "PERCEPÇÃO — o que ELE sente",
    PATTERNS: "PADRÕES, ADERÊNCIA E ESTÍMULOS",
    PLAN_WEEK: "PLANO DA SEMANA",
    COACH_MIND: "O QUE VOCÊ (coach) JÁ SABE, DISSE E DECIDIU",
}

# janela da percepção (RPE, sensação, check-ins)
_PERCEPTION_DAYS = 21

# mensagens proativas recentes do coach que entram no dossiê
_OUTBOX_DAYS = 7
_OUTBOX_LIMIT = 4
_OUTBOX_CHARS = 600

# blocos de FICHA (números) das mensagens do coach — não são a voz dele
_DATA_BLOCKS = (
    "🏃 Ritmind", "✅ Executado", "📅 Planejado", "🧩 Execução",
    "⏱️ Parciais", "👟", "🌤️", "🌡️", "🌧️", "⛈️", "🏃 Hoje é dia de treino",
)

_HISTORY_LIMIT = 30

_BODY_STATE_PT = {
    "STRAINED": "sobrecarregado (carga alta + recuperação caindo)",
    "RECOVERY_FLAG": "recuperação em queda",
    "ABSORBING": "absorvendo bem a carga (rampa saudável)",
    "BALANCED": "equilibrado (carga ótima + recuperado)",
    "FRESH": "descansado, com folga pra puxar",
    "BUILDING": "ainda montando base de dados do corpo",
}

_LIMITER_PT = {
    "sono": "sono",
    "fc_repouso": "FC de repouso subindo",
    "stress": "stress alto",
}


@dataclass
class _Inputs:
    """O que várias seções usam — carregado UMA vez por dossiê."""

    profile: str
    today: date
    runner: object = None
    history: object = None
    activities: list = field(default_factory=list)
    goal: object = None
    metrics: object = None
    plan: object = None
    reading: object = None
    trajectory: object = None
    drift: object = None
    ceiling: int | None = None
    zones: object = None


# nomes das atividades fora da corrida (Garmin) pro dossiê
_OTHER_SPORT_PT = {
    "strength_training": "musculação",
    "indoor_cardio": "cardio",
    "hiit": "HIIT",
    "cycling": "bike",
    "indoor_cycling": "bike indoor",
    "lap_swimming": "natação",
    "open_water_swimming": "natação",
    "yoga": "yoga",
    "pilates": "pilates",
    "soccer": "futebol",
    "other": "outra atividade",
}

class AthleteDossier:

    HEADER = (
        "DOSSIÊ DO ATLETA — a base ÚNICA do coach (é a MESMA que o plano, a "
        "análise dos treinos, o chat e as mensagens do dia leem). Você é o "
        "treinador dele: isto é tudo que você sabe HOJE ({today}); decida e fale "
        "com o quadro inteiro, nunca com um pedaço — e nunca contradiga o que "
        "você mesmo já decidiu/disse (seção final)."
    )

    @staticmethod
    def render(
        profile: str,
        *,
        runner=None,
        history=None,
        plan=None,
        today: date | None = None,
        exclude: tuple[str, ...] | frozenset = (),
    ) -> str:
        """O dossiê pronto pra injetar no prompt. `runner`/`history`/`plan`
        opcionais: quem já os tem passa (mesmo objeto = mesma verdade); senão
        vêm do storage. `exclude` tira seções que a tarefa já cobre do jeito
        dela (ex.: o plano da semana que vem não precisa do 'plano da semana')."""

        try:

            data = AthleteDossier._inputs(profile, runner, history, plan, today)

        except Exception as e:

            print(f"Dossiê: base do atleta falhou p/ '{profile}': {e}")

            return ""

        blocks = []

        for name in SECTIONS:

            if name in exclude:

                continue

            try:

                lines = getattr(AthleteDossier, f"_{name}")(data)

            except Exception as e:

                print(f"Dossiê ({name}) falhou p/ '{profile}': {e}")

                continue

            lines = [line for line in lines if line and line.strip()]

            if lines:

                blocks.append(f"▸ {_TITLES[name]}\n" + "\n".join(lines))

        if not blocks:

            return ""

        header = AthleteDossier.HEADER.format(
            today=f"{data.today.strftime('%d/%m/%Y')}"
        )

        return header + "\n\n" + "\n\n".join(blocks)

    # ------------------------------------------------------------------
    # base

    @staticmethod
    def _inputs(profile, runner, history, plan, today) -> _Inputs:

        from app.application.history.metrics_resolver import MetricsResolver
        from app.application.use_cases.build_training_goal import (
            BuildTrainingGoal,
        )
        from app.application.use_cases.load_runner_profile import (
            LoadRunnerProfile,
        )
        from app.core.clock import today_local
        from app.infrastructure.persistence.activity_archive_repository import (
            ActivityArchiveRepository,
        )

        data = _Inputs(profile=profile, today=today or today_local())

        data.runner = runner or LoadRunnerProfile.execute(profile)

        data.activities = ActivityArchiveRepository().load_activities(profile)

        data.history = history or AthleteDossier._archive_history(
            data.activities
        )

        data.goal = BuildTrainingGoal.execute(data.runner)

        try:

            data.metrics = MetricsResolver.resolve(data.runner, data.history)

        except Exception as e:

            print(f"Dossiê: paces falharam p/ '{profile}': {e}")

        if plan is not None:

            data.plan = plan

        else:

            from app.infrastructure.persistence.weekly_plan_repository import (
                WeeklyPlanRepository,
            )

            data.plan = WeeklyPlanRepository().load(profile)

        try:

            from app.application.coach.intelligence.body_reading_service import (
                BodyReadingService,
            )

            data.reading, data.trajectory = BodyReadingService.read(
                profile, persist=False
            )

        except Exception as e:

            print(f"Dossiê: leitura do corpo falhou p/ '{profile}': {e}")

        try:

            from app.application.history.hr_zone_resolver import HrZoneResolver
            from app.application.history.training_patterns import (
                TrainingPatterns,
            )

            data.zones = HrZoneResolver.for_profile(
                profile, data.runner, data.activities,
            )

            data.ceiling = TrainingPatterns.ceiling_of(data.zones, profile)

            data.drift = AthleteDossier._live_drift(profile, data)

        except Exception as e:

            print(f"Dossiê: régua de FC falhou p/ '{profile}': {e}")

        return data

    @staticmethod
    def _other_activities(data: _Inputs) -> str:
        """O que ele fez FORA da corrida nos últimos 7 dias (musculação, futebol,
        bike...) — não entra na carga de corrida, mas cansa: contexto pra pesar
        com a recuperação. Vazio se nada/falhou."""

        try:

            from app.application.history.weekly_buckets import activity_date
            from app.infrastructure.persistence.cross_training_repository import (
                CrossTrainingRepository,
            )

            since = data.today - timedelta(days=6)

            done: dict[str, list[float]] = {}

            for a in CrossTrainingRepository().load_activities(data.profile):

                if since <= activity_date(a) <= data.today:

                    label = _OTHER_SPORT_PT.get(a.sport, "outra atividade")

                    done.setdefault(label, []).append((a.moving_time or 0) / 60)

            if not done:

                return ""

            parts = ", ".join(
                f"{label} {len(mins)}x (~{sum(mins):.0f} min)"
                for label, mins in done.items()
            )

            return (
                f"Fora da corrida (últimos 7 dias): {parts}. Não entra na carga "
                "de corrida, mas cansa — pese junto da recuperação."
            )

        except Exception as e:

            print(f"Dossiê: outras atividades falhou p/ '{data.profile}': {e}")

            return ""

    @staticmethod
    def _open_illness(data: _Inputs):
        """Doença relatada ainda em aberto (ver IllnessEpisode). Best-effort."""

        try:

            from app.application.coach.intelligence.illness_episode import (
                IllnessEpisode,
            )

            return IllnessEpisode.open(data.profile, data.activities, data.today)

        except Exception as e:

            print(f"Dossiê: doença em aberto falhou p/ '{data.profile}': {e}")

            return None

    @staticmethod
    def _live_drift(profile: str, data: _Inputs):
        """A deriva de recuperação com a leitura de HOJE no fim da série (os
        snapshots gravados podem ainda não ter o de hoje) — senão o estado
        dizia "3 leituras seguidas em alerta" e os padrões "2", e o sono saía
        com dois números (João/Leonardo 27/09). Uma leitura só pra tudo."""

        from app.application.coach.intelligence.body_reading_service import (
            BodyReadingService,
        )
        from app.application.history.training_patterns import TrainingPatterns
        from app.core.clock import now_local
        from app.infrastructure.persistence.body_reading_history_repository import (
            BodyReadingHistoryRepository,
        )

        snapshots = [
            s for s in BodyReadingHistoryRepository().load(profile)
            if s.day < data.today
        ]

        reading = data.reading

        if reading is not None and reading.recovery.has_data:

            snapshots.append(BodyReadingService.snapshot_of(reading, now_local()))

        from app.application.history.recovery_alert_run import RecoveryAlertRun

        return TrainingPatterns.recovery_drift(
            snapshots,
            alert_since=RecoveryAlertRun.since_for_profile(
                data.profile, data.today
            ),
        )

    @staticmethod
    def _archive_history(activities):
        """O histórico do arquivo permanente (o mesmo que o LoadTrainingHistory
        une ao ao-vivo), só a pé, sem duplicata Strava×Garmin, mais novo
        primeiro — sem chamada externa."""

        from app.application.use_cases.load_training_history import (
            LoadTrainingHistory,
        )
        from app.domain.entities.training_history import TrainingHistory
        from app.domain.value_objects.sports import is_foot_sport

        runs = sorted(
            (a for a in activities if is_foot_sport(a.sport)),
            key=lambda a: a.start_date,
            reverse=True,
        )

        return TrainingHistory(
            activities=LoadTrainingHistory._dedup(runs)[:_HISTORY_LIMIT]
        )

    @staticmethod
    def _weeks_to_race(data: _Inputs) -> int | None:

        goal = data.goal

        if goal is None or goal.race_date is None or goal.race_date <= data.today:

            return None

        return (goal.race_date - data.today).days // 7

    # ------------------------------------------------------------------
    # seções

    @staticmethod
    def _who(data: _Inputs) -> list[str]:

        from app.application.coach.planning.plan_context_builder import (
            PlanContextBuilder,
        )
        from app.core.weekdays import weekday_label

        runner, goal = data.runner, data.goal

        lines = [f"Atleta: {runner.name}"]

        if goal is not None and goal.race_date and goal.race_date <= data.today:

            # prova-âncora que JÁ PASSOU não é alvo: sem isto o coach seguia
            # "periodizando" pra uma data vencida
            lines.append(
                f"Objetivo de fundo do atleta: {goal.name}. Última prova "
                f"registrada: {goal.race_label} em "
                f"{goal.race_date.strftime('%d/%m/%Y')} (JÁ PASSOU — sem prova "
                "futura marcada)."
            )

        elif goal is not None:

            days = (
                (goal.race_date - data.today).days
                if goal.race_date and goal.race_date > data.today
                else None
            )

            lines.append(
                PlanContextBuilder._goal_line(
                    goal, AthleteDossier._weeks_to_race(data), days,
                )
            )

            weeks = AthleteDossier._weeks_to_race(data)

            # dossiê da PROVA real (percurso, subidas, clima) quando ela está no
            # horizonte do bloco — só lê o cache (pesquisa é job de fundo)
            if weeks is not None and weeks <= 16:

                try:

                    from app.application.races.race_intel_service import (
                        RaceIntelService,
                    )

                    lines.append(
                        RaceIntelService.render_context(
                            RaceIntelService.for_runner(runner)
                        )
                    )

                except Exception as e:

                    print(f"Dossiê: prova falhou p/ '{data.profile}': {e}")

            try:

                from app.application.coach.planning.race_hierarchy_directive import (
                    race_hierarchy_directive,
                )

                lines.append(
                    race_hierarchy_directive(goal, getattr(runner, "goal", None))
                )

            except Exception as e:

                print(f"Dossiê: hierarquia falhou p/ '{data.profile}': {e}")

        days = list(getattr(runner, "preferred_running_days", None) or [])

        if days:

            lines.append(
                "Dias em que corre: "
                + ", ".join(weekday_label(d) for d in days)
                + f" ({len(days)}x/semana)"
            )

        if getattr(runner, "injuries", None):

            lines.append(
                "Lesões/limitações declaradas: "
                + ", ".join(runner.injuries) + "."
            )

        if getattr(runner, "external_coach", False):

            lines.append(
                "Tem TREINADOR EXTERNO: o plano é do treinador dele — o Ritmind "
                "acompanha, analisa e conversa, não monta a semana."
            )

        return lines

    @staticmethod
    def _capacity(data: _Inputs) -> list[str]:

        from app.application.coach.planning.plan_context_builder import (
            PlanContextBuilder,
        )

        lines = []

        if data.metrics is not None:

            lines.append(PlanContextBuilder._paces_line(data.metrics))

        if data.zones is not None:

            ruler = f"Régua de FC ({data.zones.method}): {data.zones.describe()} bpm"

            if data.ceiling:

                ruler += (
                    f"; teto aeróbico ~{data.ceiling} bpm (70% da reserva de FC)"
                    " — o LEVE é abaixo dele: leve/longão-base de verdade fica "
                    "abaixo do teto, e o número da zona do relógio abaixo dele "
                    "(ex.: Z3) ainda é leve/aeróbico"
                )

            lines.append(ruler)

        try:

            from app.application.coach.planning.race_projection_directive import (
                race_projection_directive,
            )
            from app.infrastructure.persistence.race_prediction_repository import (
                RacePredictionRepository,
            )

            lines.append(
                race_projection_directive(
                    RacePredictionRepository().load(data.profile), data.goal,
                )
            )

        except Exception as e:

            print(f"Dossiê: projeção falhou p/ '{data.profile}': {e}")

        return lines

    @staticmethod
    def _evolution(data: _Inputs) -> list[str]:

        lines = []

        try:

            from app.application.history.runner_baseline_builder import (
                RunnerBaselineBuilder,
            )

            base = RunnerBaselineBuilder.build(data.history, data.runner)

            # "volume real" = o que ele corre numa semana EM QUE CORRE (média
            # das últimas 4 semanas com corrida, a atual inclusa) — a base do
            # dimensionamento do plano. A TENDÊNCIA mora numa linha só (a do
            # panorama semanal, que conta semana parada como zero): antes havia
            # duas ("subindo" aqui × "12 → 7" lá) e pareciam se contradizer.
            lines.append(
                f"Volume real (numa semana em que corre — média das últimas 4 "
                f"semanas COM corrida, a atual inclusa): ~{base.weekly_km:.1f} "
                f"km/sem (última {base.last_week_km:.1f}, melhor "
                f"{base.max_week_km:.1f}); rodagem típica ~"
                f"{base.typical_run_km:.1f} km, maior treino recente ~"
                f"{base.longest_km:.1f} km."
            )

        except Exception as e:

            print(f"Dossiê: volume falhou p/ '{data.profile}': {e}")

        try:

            from app.application.history.training_reality_analyzer import (
                TrainingRealityAnalyzer,
                training_reality_directive,
            )

            lines.append(
                training_reality_directive(
                    TrainingRealityAnalyzer.assess(
                        len(data.runner.preferred_running_days or []),
                        data.history.activities,
                    )
                )
            )

        except Exception as e:

            print(f"Dossiê: realidade falhou p/ '{data.profile}': {e}")

        try:

            from app.application.coach.intelligence.fitness_reading_service import (
                FitnessReadingService,
            )
            from app.application.coach.planning.fitness_directive import (
                fitness_plan_directive,
            )
            from app.application.coach.writer.fitness_evolution_writer import (
                FitnessEvolutionWriter,
            )

            evolution = FitnessReadingService.read_evolution(data.profile)

            line = FitnessEvolutionWriter.line(evolution)

            if line:

                lines.append(f"Evolução da forma: {line}")

            lines.append(fitness_plan_directive(evolution))

        except Exception as e:

            print(f"Dossiê: forma falhou p/ '{data.profile}': {e}")

        from app.application.history.weekly_evolution_digest import (
            WeeklyEvolutionDigest,
        )

        lines.append(WeeklyEvolutionDigest.for_profile(data.profile))

        try:

            from app.infrastructure.persistence.activity_archive_repository import (
                ActivityArchiveRepository,
            )

            stats = ActivityArchiveRepository().stats(data.profile)

            if stats:

                first = stats["first_date"]

                lines.append(
                    f"Histórico geral registrado: {stats['total_runs']} treinos, "
                    f"{stats['total_km']:.0f} km desde {first[5:7]}/{first[:4]}; "
                    f"maior treino: {stats['longest_km']:.1f} km."
                )

        except Exception as e:

            print(f"Dossiê: histórico geral falhou p/ '{data.profile}': {e}")

        return lines

    @staticmethod
    def _body(data: _Inputs) -> list[str]:
        """O corpo agora: estado, piora real vs a base dele, sono (e se o sono
        curto derruba a entrega DELE), risco de lesão, prehab e sinal de
        descarga — tudo como leitura + conhecimento, a decisão é da IA."""

        from app.application.coach.planning.body_directive import (
            body_plan_directive,
        )

        reading = data.reading

        lines = []

        if reading is not None:

            state = _BODY_STATE_PT.get(reading.body_state)

            if state:

                limiter = (
                    _LIMITER_PT.get(reading.limiter)
                    if reading.limiter
                    else None
                )

                acwr = getattr(reading.load, "acwr", None)

                extra = f"; limitador: {limiter}" if limiter else ""

                extra += f"; carga aguda/crônica (ACWR) {acwr:.2f}" if acwr else ""

                low_base = getattr(reading.load, "low_base", None)

                if isinstance(low_base, tuple):

                    extra += (
                        f" — razão alta só pela base BAIXA (~{low_base[0]} min/"
                        f"semana, {low_base[1]:+d} min reais nesta): NÃO é pico "
                        "de carga"
                    )

                if reading.body_state == "ABSORBING" and acwr and acwr > 1.3:

                    # absorvendo = a RECUPERAÇÃO está em dia; com a carga subindo
                    # rápido, "rampa saudável" contradiz o risco de lesão abaixo
                    state = "recuperação em dia, mas a carga subiu rápido"

                lines.append(f"Estado: {state}{extra}.")

        other = AthleteDossier._other_activities(data)

        if other:

            lines.append(other)

        ill = AthleteDossier._open_illness(data)

        if ill is not None:

            lines.append(
                f"DOENÇA EM ABERTO: ele relatou estar doente em "
                f"{ill.day[8:10]}/{ill.day[5:7]}"
                + (f' ("{ill.note}")' if ill.note else "")
                + " e NÃO correu desde então — o estado acima é da CARGA (ele "
                "parou), não da saúde: não é folga pra puxar. Quando voltar, "
                "retorno leve e curto; se ainda estiver doente, descanso."
            )

        if reading is not None:

            lines.append(
                body_plan_directive(
                    reading, data.trajectory, data.drift, data.ceiling,
                )
            )

        try:

            from app.application.coach.intelligence.sleep_reading_service import (
                SleepReadingService,
            )

            sleep = SleepReadingService.read(data.profile)

            if sleep.has_data and sleep.avg_hours is not None:

                trend = {"rising": "melhorando", "falling": "caindo"}.get(
                    sleep.direction, "estável"
                )

                debt = " (abaixo do que o corpo pede)" if sleep.debt else ""

                lines.append(f"Sono: ~{sleep.avg_hours:.1f}h/noite, {trend}{debt}.")

        except Exception as e:

            print(f"Dossiê: sono falhou p/ '{data.profile}': {e}")

        # SONO × EXECUÇÃO: o sono curto DESTE atleta derruba a entrega dele?
        # Com piora REAL da recuperação, "o sono não pesa na execução" contradiz
        # a leitura acima — a fisiologia piorando vale mais (a execução é a
        # última a cair). Varredura 26/09.
        strained = reading is not None and reading.body_state == "STRAINED"

        if not strained and not (data.drift is not None and data.drift.worsening):

            try:

                from app.application.coach.intelligence.fitness_reading_service import (
                    FitnessReadingService,
                )
                from app.application.history.sleep_performance_analyzer import (
                    SleepPerformanceAnalyzer,
                    sleep_performance_directive,
                )

                activities, series, resting_hr, max_hr = (
                    FitnessReadingService._load(data.profile)
                )

                lines.append(
                    sleep_performance_directive(
                        SleepPerformanceAnalyzer.assess(
                            activities, series, resting_hr, max_hr,
                        )
                    )
                )

            except Exception as e:

                print(f"Dossiê: sono×execução falhou p/ '{data.profile}': {e}")

        if reading is None:

            return lines

        try:

            from app.application.history.injury_risk_analyzer import (
                InjuryRiskAnalyzer,
                injury_risk_directive,
            )
            from app.infrastructure.persistence.form_fatigue_store import (
                FormFatigueStore,
            )

            risk = InjuryRiskAnalyzer.assess(
                reading.load,
                reading.recovery,
                getattr(data.runner, "injuries", None),
                form_fading=FormFatigueStore().is_fading(data.profile),
            )

            lines.append(injury_risk_directive(risk))

            lines.append(AthleteDossier._prehab(data, risk))

        except Exception as e:

            print(f"Dossiê: risco de lesão falhou p/ '{data.profile}': {e}")

        # atleta de treinador externo: não sinalizamos descarga sobre um plano
        # que não montamos
        if not getattr(data.runner, "external_coach", False):

            try:

                from app.application.coach.planning.ai_plan_service import (
                    AIPlanService,
                )
                from app.application.history.deload_analyzer import (
                    DeloadAnalyzer,
                    deload_directive,
                )

                week_start = data.today - timedelta(days=data.today.weekday())

                lines.append(
                    deload_directive(
                        DeloadAnalyzer.assess(
                            reading.load.weekly_loads,
                            reading.recovery,
                            weeks_to_race=AthleteDossier._weeks_to_race(data),
                            acwr=getattr(reading.load, "acwr", None),
                            weeks_since_race=AIPlanService._weeks_since_race(
                                data.profile, data.history, week_start,
                            ),
                        )
                    )
                )

            except Exception as e:

                print(f"Dossiê: descarga falhou p/ '{data.profile}': {e}")

        return lines

    @staticmethod
    def _prehab(data: _Inputs, risk) -> str:
        """Dor relatada → exercícios da área; senão risco elevado → prehab
        geral; senão nada."""

        from app.application.coach.intelligence.prehab_advisor import (
            PrehabAdvisor,
        )
        from app.infrastructure.persistence.checkin_repository import (
            CheckinRepository,
        )

        checkin = CheckinRepository().latest_recent(
            data.profile, data.today.isoformat()
        )

        if checkin is not None and (checkin.soreness or 0) >= 2:

            return PrehabAdvisor.directive_for_pain(checkin.note or "")

        if getattr(risk, "elevated", False):

            return PrehabAdvisor.directive_general()

        return ""

    @staticmethod
    def _perception(data: _Inputs) -> list[str]:
        """O que ELE sente — esforço percebido dos treinos (relógio, resposta
        ou conversa), sensação, check-ins (energia/sono/dor/doença). É a
        terceira perna (evolução × objetivo × PERCEPÇÃO)."""

        from app.application.coach.intelligence.checkin_service import (
            CheckinService,
        )
        from app.application.coach.conversation.rpe_flow import RpeFlow
        from app.core.weekdays import weekday_label, weekday_name
        from app.infrastructure.persistence.checkin_repository import (
            CheckinRepository,
        )
        from app.infrastructure.persistence.session_rpe_repository import (
            SessionRpeRepository,
        )

        cutoff = data.today - timedelta(days=_PERCEPTION_DAYS)

        def label(day: str) -> str:

            parsed = date.fromisoformat(day)

            return f"{weekday_label(weekday_name(parsed))} {parsed.strftime('%d/%m')}"

        lines = []

        sessions = sorted(
            SessionRpeRepository().load_sessions(data.profile),
            key=lambda s: s.day,
        )

        recent = [s for s in sessions if date.fromisoformat(s.day) >= cutoff]

        for s in recent:

            bits = []

            if s.rpe is not None:

                bits.append(f"esforço percebido {s.rpe}/10")

            feel = getattr(s, "feel", None)

            if feel:

                bits.append(f"sensação {feel}")

            note = getattr(s, "note", None)

            if note:

                bits.append(f'"{note}"')

            source = getattr(s, "source", None)

            origin = f" ({source})" if source and source != "resposta" else ""

            if bits:

                lines.append(f"- {label(s.day)}: {', '.join(bits)}{origin}")

        for c in sorted(CheckinRepository().load(data.profile), key=lambda x: x.day):

            if not getattr(c, "has_data", False):

                continue

            if date.fromisoformat(c.day) < cutoff:

                continue

            bits = []

            if c.energy is not None:

                bits.append(f"energia {c.energy}/5")

            if c.sleep_quality is not None:

                bits.append(f"sono {c.sleep_quality}/5")

            if c.soreness:

                bits.append(f"dor nível {c.soreness}")

            if getattr(c, "illness", False):

                bits.append("doente")

            if getattr(c, "note", None):

                bits.append(f'"{c.note}"')

            if bits:

                lines.append(f"- {label(c.day)} (check-in): {', '.join(bits)}")

        if not lines:

            return [
                "Sem relato de esforço/sensação nas últimas 3 semanas — você "
                "está sem a percepção dele. Quando fizer sentido, pergunte como "
                "ele se sentiu (natural, sem formulário)."
            ]

        out = [
            "Relatos recentes (pese JUNTO do corpo/carga: esforço alto pro que "
            "a carga diz = está sentindo mais, cuidado; baixo ou boa energia = "
            "sobra pra dosar mais):"
        ] + lines

        out.append(CheckinService.render_recent(data.profile))

        out.append(RpeFlow.recent_note(data.profile))

        return out

    @staticmethod
    def _patterns(data: _Inputs) -> list[str]:

        from app.application.coach.planning.plan_context_builder import (
            PlanContextBuilder,
        )
        from app.application.history.adherence_analyzer import AdherenceAnalyzer
        from app.application.history.execution_log import ExecutionLog
        from app.application.history.stimulus_ledger import StimulusLedger
        from app.application.history.training_patterns import TrainingPatterns
        from app.application.planner.weekly_plan_service import (
            WeeklyPlanService,
        )
        from app.infrastructure.persistence.weekly_plan_repository import (
            WeeklyPlanRepository,
        )

        lines = []

        repository = WeeklyPlanRepository()

        week_start = data.today - timedelta(days=data.today.weekday())

        try:

            adherence = WeeklyPlanService._recent_adherence(
                data.profile, repository, data.history, week_start,
            )

            if adherence:

                lines.append(PlanContextBuilder._adherence_line(adherence))

            lines.append(
                PlanContextBuilder._missed_pattern_line(
                    AdherenceAnalyzer.analyze(
                        repository.history(data.profile),
                        data.history,
                        until_week=week_start - timedelta(days=7),
                    )
                )
            )

        except Exception as e:

            print(f"Dossiê: aderência falhou p/ '{data.profile}': {e}")

        lines.append(TrainingPatterns.for_profile(data.profile, drift=data.drift))

        # sessão a sessão, o alvo × o feito — de onde sai a calibração e a
        # leitura de evolução (a IA lê e decide; nada de viés pronto)
        lines.append(ExecutionLog.for_profile(data.profile))

        lines.append(StimulusLedger.for_profile(data.profile))

        return lines

    @staticmethod
    def _plan_week(data: _Inputs) -> list[str]:
        """A semana do plano, com feito × não feito validado no histórico real
        (não assume que passou = feito) e o propósito de cada sessão."""

        from app.application.planner.weekly_plan_matcher import (
            WeeklyPlanMatcher,
        )
        from app.application.planner.weekly_plan_message_formatter import (
            WeeklyPlanMessageFormatter,
        )

        plan = data.plan

        if plan is None or not plan.sessions:

            return ["Sem plano da semana registrado."]

        activities = data.history.activities

        done_days = WeeklyPlanMatcher.fulfilled_days(plan, activities)

        WeeklyPlanMatcher.hydrate_executed(plan, activities)

        stale = plan.week_start + timedelta(days=6) < data.today

        if stale:

            header = (
                f"Plano da semana de {plan.week_start.strftime('%d/%m')} (JÁ "
                "ENCERRADA — ainda não há plano desta semana; as datas abaixo "
                "são passadas):"
            )

        else:

            header = (
                f"Semana de {plan.week_start.strftime('%d/%m')}"
                + (f" — fase {plan.phase}" if getattr(plan, "phase", None) else "")
                + ":"
            )

        lines = [header]

        lines.extend(
            WeeklyPlanMessageFormatter.session_lines(
                plan, data.today, done_days=done_days,
            )
        )

        if getattr(plan, "source", None) == "externo":

            lines.append(
                "(plano do treinador dele — o Ritmind só acompanha"
                + ("; aguardando o plano desta semana)" if stale else ")")
            )

        return lines

    @staticmethod
    def _coach_mind(data: _Inputs) -> list[str]:
        """Memória do atleta (o que ele contou), por que ele corre, o que o
        coach aprendeu observando, o que já cobrou, o que já disse por conta
        própria (análise, bom dia, plano) e o resumo das conversas — pra toda
        voz saber o que as outras disseram e não se contradizer."""

        from app.application.coach.memory.runner_memory_service import (
            RunnerMemoryService,
        )
        from app.core.config import get_settings
        from app.infrastructure.persistence.coach_attention_log import (
            CoachAttentionLog,
        )

        lines = [
            RunnerMemoryService.render(data.profile),
            RunnerMemoryService.motivation_anchor(data.profile),
        ]

        if get_settings().coach_learning_inject_enabled:

            from app.application.coach.memory.coach_learning_service import (
                CoachLearningService,
            )

            lines.append(CoachLearningService.render(data.profile))

        lines.append(CoachAttentionLog.render(data.profile, data.today))

        lines.append(AthleteDossier._recent_coach_messages(data))

        try:

            from app.infrastructure.persistence.conversation_repository import (
                ConversationRepository,
            )

            summary = ConversationRepository().load_summary(data.profile)["summary"]

            if summary:

                lines.append(f"Resumo das conversas com ele: {summary}")

        except Exception as e:

            print(f"Dossiê: resumo de conversa falhou p/ '{data.profile}': {e}")

        return lines

    @staticmethod
    def _recent_coach_messages(data: _Inputs) -> str:

        from datetime import datetime

        from app.infrastructure.persistence.coach_outbox_repository import (
            CoachOutboxRepository,
        )

        cutoff = data.today - timedelta(days=_OUTBOX_DAYS)

        picked = []

        for entry in CoachOutboxRepository().recent(data.profile, 12):

            stamp = str(entry.get("timestamp") or "")

            try:

                day = datetime.fromisoformat(stamp).date()

            except ValueError:

                day = None

            if day is not None and day < cutoff:

                continue

            text = AthleteDossier._coach_voice_only(str(entry.get("text", "")))

            if not text:

                continue

            if len(text) > _OUTBOX_CHARS:

                text = text[:_OUTBOX_CHARS] + "…"

            when = day.strftime("%d/%m") if day else "recente"

            picked.append(f"- {when}: {text}")

        picked = picked[-_OUTBOX_LIMIT:]

        if not picked:

            return ""

        return (
            "O que você já mandou pra ele por conta própria (análise, bom dia, "
            "plano, revisão) — não repita, não contradiga sem explicar o que "
            "mudou:\n" + "\n".join(picked)
        )

    @staticmethod
    def _coach_voice_only(text: str) -> str:
        """Da mensagem enviada, só o que o COACH disse (abertura, análise,
        ponto de atenção, próximo passo, recado) — sem a ficha de números
        (Executado/Planejado/parciais/blocos), que já está no dossiê. Antes o
        corte em N caracteres pegava só a ficha e a opinião sumia. Sem nada de
        voz (ficha pura), devolve o começo cru."""

        blocks = [b.strip() for b in text.replace("\r", "").split("\n\n")]

        kept = []

        for block in blocks:

            if not block or block.startswith(_DATA_BLOCKS):

                continue

            first = block.split("\n", 1)[0]

            # bloco de sessão prescrita (bom dia/plano): a semana já está no
            # dossiê — fica só a linha de recado, se houver
            if "🔹" in first and "\n" in block:

                continue

            kept.append(block)

        voice = " ".join(" ".join(kept).split())

        return voice or " ".join(text.split())[:300]
