from datetime import timedelta

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.history.metrics_resolver import (
    MetricsResolver,
)
from app.application.planner.weekly_plan_matcher import (
    WeeklyPlanMatcher,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.planner.weekly_plan_service import (
    WeeklyPlanService,
)
from app.application.use_cases.build_training_goal import (
    BuildTrainingGoal,
)
from app.application.use_cases.load_runner_profile import (
    LoadRunnerProfile,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.core.weekdays import weekday_label, weekday_name
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.coach_outbox_repository import (
    CoachOutboxRepository,
)
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)


class ConversationContextBuilder:

    @staticmethod
    async def build(
        profile: str,
        incoming_text: str = "",
    ) -> str:

        runner = LoadRunnerProfile.execute(profile)

        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = MetricsResolver.resolve(
            runner,
            history,
        )

        goal = BuildTrainingGoal.execute(runner)

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            history=history,
        )

        today = today_local()

        # ÂNCORA DE DATA: a IA NÃO calcula datas — ela LÊ. Damos hoje, amanhã
        # e ontem JÁ RESOLVIDOS (dia da semana + data). Sem isto, mesmo com
        # "hoje" dado, o Flash deduzia "amanhã" a partir das DATAS DO PLANO
        # (viu o plano começando terça 14/07 e concluiu "hoje = segunda 13/07")
        # — bug real do Renato, domingo virou segunda. Data errada é linha
        # vermelha: nunca pode acontecer.
        tomorrow = today + timedelta(days=1)

        yesterday = today - timedelta(days=1)

        def _date_line(day):
            return f"{weekday_label(weekday_name(day))}, {day.strftime('%d/%m/%Y')}"

        facts = (
            "DATAS — use EXATAMENTE estas, NUNCA recalcule o dia da semana:\n"
            f"- HOJE é {_date_line(today)}.\n"
            f"- AMANHÃ é {_date_line(tomorrow)}.\n"
            f"- ONTEM foi {_date_line(yesterday)}.\n"
            # calendário resolvido: sem isto, quando o atleta cita um dia
            # QUALQUER ("sexta", "terça que vem"), a IA tinha que calcular a
            # data sozinha e às vezes pescava um dia do CRONOGRAMA do plano —
            # bug real do Renato (pediu "amanhã→sexta", o coach propôs "terça",
            # dia que já tinha passado). Agora todo dia da semana vem resolvido.
            + ConversationContextBuilder._week_calendar(today)
            + "As datas do plano mais abaixo são o CRONOGRAMA da semana — elas "
            "NÃO são 'hoje'. Para 'hoje/amanhã/ontem/esta semana' use SÓ as três "
            "linhas acima; JAMAIS deduza o dia atual a partir das datas do "
            "plano.\n"
            f"Corredor: {runner.name}\n"
            f"Meta: {runner.goal}\n"
            f"Volume semanal atual: {assessment.current_weekly_volume:.1f} km "
            f"(meta recomendada: {assessment.recommended_weekly_volume:.1f} km)\n"
            f"Consistência: {assessment.consistency:.0f}%\n"
            f"Último treino: {ConversationContextBuilder._last_activity_summary(history)}\n"
            f"Próximo treino planejado: {ConversationContextBuilder._next_session_summary(plan, history)}\n"
        )

        # Status do treino de HOJE: sem isto o coach não sabe que a sessão de
        # hoje já foi feita+analisada e trata o atleta como se estivesse no
        # MEIO do treino ("termine os tiros") — bug real do Renato.
        today_status = ConversationContextBuilder._today_training_status(
            plan,
            history,
        )

        if today_status:

            facts = f"{facts}{today_status}\n"

        race_line = ConversationContextBuilder._race_summary(goal)

        if race_line:

            facts = f"{facts}{race_line}\n"

        week_plan = ConversationContextBuilder._week_plan_summary(
            plan,
            history,
        )

        if week_plan:

            facts = f"{facts}\n{week_plan}\n"

        # o que o COACH mandou por conta própria (análise, briefing, plano) —
        # não está no histórico de chat, mas o atleta comenta sobre isso
        recent_coach = ConversationContextBuilder._recent_coach_messages(
            profile,
        )

        if recent_coach:

            facts = f"{facts}\n{recent_coach}\n"

        lifetime = ConversationContextBuilder._lifetime_summary(
            profile,
        )

        if lifetime:

            facts = f"{facts}{lifetime}\n"

        # quebra MENSAL do histórico — só quando o atleta pergunta sobre um
        # período ("quantos km em maio?", "corri mais mês passado?"). Fora
        # disso não entra, pra não inflar o prompt do chat. Ver
        # [[project_consumo_tokens]].
        history_digest = ConversationContextBuilder._history_digest(
            profile,
            incoming_text,
        )

        if history_digest:

            facts = f"{facts}\n{history_digest}\n"

        # O QUADRO COMPLETO do atleta (evolução + corpo + sono + o que o coach
        # aprendeu): o coach de CONVERSA tem que raciocinar como TREINADOR — com
        # a trajetória inteira na cabeça —, não responder olhando só o dia. Best-
        # effort: cada peça que falhar simplesmente não entra. Ver item "coach
        # considera plano/evolução/dia-a-dia".
        state = ConversationContextBuilder._athlete_state(profile)

        if state:

            facts = f"{facts}\n{state}\n"

        memory = RunnerMemoryService.render(profile)

        if memory:

            facts = f"{facts}\n{memory}\n"

        # a ÂNCORA EMOCIONAL (por que ele corre) — seção própria, pra o coach
        # CONHECER o atleta e puxar o porquê dele nos momentos que importam.
        anchor = RunnerMemoryService.motivation_anchor(profile)

        if anchor:

            facts = f"{facts}\n{anchor}\n"

        summary = ConversationRepository().load_summary(
            profile,
        )["summary"]

        if summary:

            facts = (
                f"{facts}\nResumo de conversas anteriores: "
                f"{summary}\n"
            )

        return facts

    @staticmethod
    def _week_calendar(today) -> str:
        """Calendário RESOLVIDO da semana atual + a próxima (dia da semana →
        data), marcando HOJE/amanhã/ontem e o que JÁ PASSOU. A IA não calcula
        data nenhuma — lê daqui. Fecha o buraco de quando o atleta cita um dia
        qualquer ('sexta', 'terça que vem') e a IA chutava/pescava do plano."""

        monday = today - timedelta(days=today.weekday())

        lines = [
            "CALENDÁRIO (use estas datas para QUALQUER dia da semana citado; "
            "NUNCA proponha um dia que JÁ PASSOU):",
        ]

        for offset in range(14):

            day = monday + timedelta(days=offset)

            if offset == 0:

                lines.append("Esta semana:")

            elif offset == 7:

                lines.append("Próxima semana:")

            label = weekday_label(weekday_name(day))

            if day == today:

                mark = " ← HOJE"

            elif day == today + timedelta(days=1):

                mark = " ← amanhã"

            elif day < today:

                mark = " (já passou)"

            else:

                mark = ""

            lines.append(f"- {label} {day.strftime('%d/%m')}{mark}")

        return "\n".join(lines) + "\n"

    # estado do corpo (veredito) traduzido pro coach de conversa
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

    @staticmethod
    def _athlete_state(profile: str) -> str:
        """O quadro completo pro coach de conversa: evolução (forma), corpo/
        recuperação, sono e o que o coach APRENDEU observando o atleta. Tudo
        determinístico e já pronto — aqui só rende compacto. Best-effort."""

        lines: list[str] = []

        try:

            from app.application.coach.intelligence.fitness_reading_service import (
                FitnessReadingService,
            )
            from app.application.coach.writer.fitness_evolution_writer import (
                FitnessEvolutionWriter,
            )

            evo_line = FitnessEvolutionWriter.line(
                FitnessReadingService.read_evolution(profile)
            )

            if evo_line:

                lines.append(f"- Evolução da forma: {evo_line}")

        except Exception as e:

            print(f"Estado (evolução) falhou p/ '{profile}': {e}")

        try:

            from app.application.coach.intelligence.body_reading_service import (
                BodyReadingService,
            )

            reading, _ = BodyReadingService.read(profile, persist=False)

            state = ConversationContextBuilder._BODY_STATE_PT.get(
                reading.body_state
            )

            if state:

                # o sono tem LINHA PRÓPRIA abaixo (mais detalhada); não repete
                # aqui como "ponto de atenção" — evita dizer sono 2x no quadro
                limiter = (
                    ConversationContextBuilder._LIMITER_PT.get(reading.limiter)
                    if reading.limiter and reading.limiter != "sono"
                    else None
                )

                extra = f"; ponto de atenção: {limiter}" if limiter else ""

                lines.append(f"- Corpo/recuperação: {state}{extra}")

            # risco de lesão precoce (reusa a leitura do corpo + histórico)
            from app.application.history.injury_risk_analyzer import (
                InjuryRiskAnalyzer,
                injury_risk_chat_line,
            )
            from app.infrastructure.persistence.form_fatigue_store import (
                FormFatigueStore,
            )

            runner = LoadRunnerProfile.execute(profile)

            risk = InjuryRiskAnalyzer.assess(
                reading.load,
                reading.recovery,
                getattr(runner, "injuries", None),
                form_fading=FormFatigueStore().is_fading(profile),
            )

            risk_line = injury_risk_chat_line(risk)

            if risk_line:

                lines.append(risk_line)

            # FORÇA/MOBILIDADE PREVENTIVA (prehab): se o atleta relatou dor, dá
            # exercícios da área; senão, se o risco está elevado, prehab geral.
            # É o "o que fazer" que faltava — não só "segure a carga".
            prehab = ConversationContextBuilder._prehab_line(profile, risk)

            if prehab:

                lines.append(prehab)

            # DESCARGA proativa: se a semana é de recuperação planejada, o coach
            # precisa saber (e saber explicar) por que o plano está mais leve.
            from app.application.history.deload_analyzer import (
                DeloadAnalyzer,
                deload_chat_line,
            )
            from app.application.use_cases.build_training_goal import (
                BuildTrainingGoal,
            )

            goal = BuildTrainingGoal.execute(runner)

            today = today_local()

            weeks_to_race = (
                (goal.race_date - today).days // 7
                if goal.race_date and goal.race_date > today
                else None
            )

            # atleta de treinador externo: o plano é do treinador dele — não
            # anunciamos "descarga" sobre um plano que não montamos
            if not getattr(runner, "external_coach", False):

                deload_line = deload_chat_line(
                    DeloadAnalyzer.assess(
                        reading.load.weekly_loads,
                        reading.recovery,
                        weeks_to_race=weeks_to_race,
                    )
                )

                if deload_line:

                    lines.append(deload_line)

        except Exception as e:

            print(f"Estado (corpo) falhou p/ '{profile}': {e}")

        try:

            from app.application.coach.intelligence.sleep_reading_service import (
                SleepReadingService,
            )

            sr = SleepReadingService.read(profile)

            if sr.has_data and sr.avg_hours is not None:

                trend = {"rising": "melhorando", "falling": "caindo"}.get(
                    sr.direction, "estável"
                )

                debt = " (abaixo do que o corpo pede)" if sr.debt else ""

                lines.append(
                    f"- Sono: ~{sr.avg_hours:.1f}h/noite, {trend}{debt}"
                )

        except Exception as e:

            print(f"Estado (sono) falhou p/ '{profile}': {e}")

        try:

            from app.core.config import get_settings

            if get_settings().coach_learning_inject_enabled:

                from app.application.coach.memory.coach_learning_service import (
                    CoachLearningService,
                )

                learnings = CoachLearningService.render(profile)

                if learnings:

                    lines.append(learnings)

        except Exception as e:

            print(f"Estado (aprendizados) falhou p/ '{profile}': {e}")

        if not lines:

            return ""

        return (
            "QUADRO ATUAL DO ATLETA (você é o TREINADOR dele — considere SEMPRE "
            "a trajetória inteira ao analisar, propor e responder, nunca só o "
            "dia de hoje):\n" + "\n".join(lines)
        )

    @staticmethod
    def _prehab_line(profile: str, risk) -> str:
        """Prehab pro quadro do coach: dor relatada -> exercícios da área;
        senão, risco elevado -> prehab geral; senão nada. Best-effort."""

        try:

            from app.application.coach.intelligence.prehab_advisor import (
                PrehabAdvisor,
            )
            from app.core.clock import today_local
            from app.infrastructure.persistence.checkin_repository import (
                CheckinRepository,
            )

            checkin = CheckinRepository().latest_recent(
                profile, today_local().isoformat()
            )

            sore = checkin is not None and (checkin.soreness or 0) >= 2

            if sore:

                note = checkin.note or ""

                return PrehabAdvisor.directive_for_pain(note)

            if getattr(risk, "elevated", False):

                return PrehabAdvisor.directive_general()

        except Exception as e:

            print(f"Prehab falhou p/ '{profile}': {e}")

        return ""

    @staticmethod
    def _race_summary(
        goal,
        reference_date=None,
    ) -> str:
        """Prova alvo, quando existir e for futura — atleta sem prova
        não tem essa linha (nada é inventado)."""

        if goal.race_date is None:

            return ""

        today = reference_date or today_local()

        if goal.race_date <= today:

            return ""

        weeks = (goal.race_date - today).days // 7

        target = (
            f", alvo {goal.target_time}" if goal.target_time else ""
        )

        # a META já aparece no cabeçalho ("Meta: ..."); aqui só ancoramos a
        # DATA-alvo, sem repetir a frase inteira da meta como "nome da prova"
        return (
            f"Data-alvo da meta: "
            f"{goal.race_date.strftime('%d/%m/%Y')} "
            f"(daqui a {weeks} semanas{target})\n"
        )

    @staticmethod
    def _lifetime_summary(
        profile: str,
    ) -> str:
        """Agregados do arquivo permanente — o coach responde sobre o
        histórico de vida, além da janela recente do Strava."""

        stats = ActivityArchiveRepository().stats(profile)

        if stats is None:

            return ""

        first = stats["first_date"]

        first_label = f"{first[5:7]}/{first[:4]}"  # mm/aaaa

        return (
            f"Histórico geral registrado: {stats['total_runs']} "
            f"treinos, {stats['total_km']:.0f} km desde "
            f"{first_label}; maior treino: "
            f"{stats['longest_km']:.1f} km\n"
        )

    @staticmethod
    def _history_digest(
        profile: str,
        incoming_text: str,
    ) -> str:
        """Tabela mês-a-mês das corridas arquivadas — aterra o coach pra
        responder pergunta de período com verdade. Só entra quando a mensagem
        PARECE histórica (portão barato), pra o prompt do chat seguir enxuto.
        Best-effort: falhar aqui nunca derruba a conversa."""

        from app.application.coach.conversation.history_query_detector import (
            HistoryQueryDetector,
        )

        if not HistoryQueryDetector.looks_historical(incoming_text):

            return ""

        try:

            from app.application.history.monthly_training_digest import (
                MonthlyTrainingDigest,
            )

            activities = ActivityArchiveRepository().load_activities(profile)

            return MonthlyTrainingDigest.render(activities, today_local())

        except Exception as e:

            print(f"Digest mensal falhou p/ '{profile}': {e}")

            return ""

    @staticmethod
    def _week_plan_summary(
        plan,
        history,
    ) -> str:
        """Plano completo da semana — permite ao coach responder
        "qual meu treino de sábado?" sem inventar. Marca feito x não feito
        validando o histórico real (não assume que passou = feito)."""

        if not plan.sessions:

            return ""

        done_days = WeeklyPlanMatcher.fulfilled_days(
            plan,
            history.activities,
        )

        today = today_local()

        # plano de uma semana já encerrada (ex.: treinador externo que ainda
        # não mandou o desta semana). Deixa explícito, pra o coach NÃO recitar
        # como se fosse a semana atual. O que decide é a SEMANA ter acabado —
        # não as sessões estarem no passado: quem treina seg/qua/qui tem, na
        # sexta, um plano vigente com todas as sessões atrás, e ouvir "ainda
        # não há plano desta semana" seria mentira.
        is_stale = plan.week_start + timedelta(days=6) < today

        if is_stale:

            header = (
                f"Plano da semana de {plan.week_start.strftime('%d/%m')} "
                "(JÁ ENCERRADA — ainda não há plano desta semana; as datas "
                "abaixo são passadas):"
            )

        else:

            header = "Plano da semana completo:"

        lines = [header]

        lines.extend(
            WeeklyPlanMessageFormatter.session_lines(
                plan,
                today,
                done_days=done_days,
            )
        )

        if plan.source == "externo":

            note = (
                "(plano montado pelo treinador do corredor — o "
                "Ritmind só acompanha"
            )

            note += (
                "; aguardando o print do plano desta semana)"
                if is_stale
                else ")"
            )

            lines.append(note)

        return "\n".join(lines)

    @staticmethod
    def _last_activity_summary(
        history,
        reference_date=None,
    ) -> str:

        latest = history.latest

        if latest is None:

            return "nenhum treino recente encontrado"

        distance_km = latest.distance / 1000

        # data (e marca HOJE) pra o coach saber se o treino já foi feito hoje —
        # sem isso "Corrida da tarde, 6 km" não diz QUANDO foi.
        today = reference_date or today_local()

        activity_day = latest.start_date.date()

        when = (
            " (HOJE)"
            if activity_day == today
            else f" ({activity_day.strftime('%d/%m')})"
        )

        return f"{latest.name}, {distance_km:.1f} km{when}"

    @staticmethod
    def _today_training_status(
        plan,
        history,
        reference_date=None,
    ) -> str:
        """Status do treino de HOJE: concluído (feito + já analisado), pendente
        ou descanso. É o que impede o coach de tratar o atleta como se estivesse
        no MEIO da sessão quando ele comenta um treino que JÁ acabou."""

        today = reference_date or today_local()

        session = next(
            (
                s
                for s in plan.sessions
                if plan.session_date(s) == today
            ),
            None,
        )

        # descanso hoje (ou plano de outra semana): sem linha
        if session is None:

            return ""

        fulfilled = {
            day.lower()
            for day in WeeklyPlanMatcher.fulfilled_days(
                plan,
                history.activities,
            )
        }

        if session.day.lower() in fulfilled:

            return (
                f"Treino de HOJE ({session.workout_type}): JÁ CONCLUÍDO — o "
                "atleta já treinou e JÁ RECEBEU a análise deste treino. NÃO "
                "peça pra ele 'terminar' nem oriente como se estivesse no meio "
                "da sessão; qualquer comentário dele sobre este treino é "
                "PÓS-treino (relato/ajuste do que já aconteceu)."
            )

        return (
            f"Treino de HOJE ({session.workout_type}): ainda NÃO registrado "
            "(o atleta pode não ter feito ainda, ou não sincronizou)."
        )

    @staticmethod
    def _recent_coach_messages(
        profile: str,
        limit: int = 2,
        max_chars: int = 700,
    ) -> str:
        """As últimas mensagens AUTOMÁTICAS que o coach enviou (análise,
        briefing, plano) — não entram no histórico de chat, mas o atleta
        comenta sobre elas. Compactadas numa linha e truncadas pra não inflar
        o contexto."""

        entries = CoachOutboxRepository().recent(profile, limit)

        if not entries:

            return ""

        lines = [
            "MENSAGENS QUE VOCÊ (coach) JÁ ENVIOU ao atleta recentemente "
            "(análise/briefing/plano — NÃO estão no histórico de chat acima, "
            "mas o atleta pode comentar sobre elas; reconheça o que já disse "
            "em vez de repetir tudo):"
        ]

        for entry in entries:

            text = " ".join(str(entry.get("text", "")).split())

            if len(text) > max_chars:

                text = text[:max_chars] + "…"

            lines.append(f"- {text}")

        return "\n".join(lines)

    @staticmethod
    def _next_session_summary(
        plan,
        history,
        reference_date=None,
    ) -> str:

        if not plan.sessions:

            return "nenhum treino planejado ainda"

        today = reference_date or today_local()

        done_days = {
            day.lower()
            for day in WeeklyPlanMatcher.fulfilled_days(
                plan,
                history.activities,
            )
        }

        upcoming = sorted(
            plan.sessions,
            key=lambda session: plan.session_date(session),
        )

        # próximo = 1ª sessão futura ainda NÃO cumprida. Sem fallback pra
        # sessão passada (não apresentar data velha como "próximo treino").
        session = next(
            (
                s
                for s in upcoming
                if plan.session_date(s) >= today
                and s.day.lower() not in done_days
            ),
            None,
        )

        if session is None:

            return "sem treino planejado restante nesta semana"

        session_date = plan.session_date(session)

        # Marca EXPLÍCITA de hoje/amanhã: sem isto o modelo lê "Próximo treino
        # ... 14/07" e, mesmo com HOJE=14/07 na âncora, chama de "amanhã" (a
        # palavra "próximo" o empurra pro futuro e ele não cruza as datas com
        # thinking_budget=0). Bug real do Renato (2026-07-14). Data errada é
        # linha vermelha — ver feedback_validar_datas_sempre.
        if session_date == today:

            when = " [É HOJE]"

        elif session_date == today + timedelta(days=1):

            when = " [É AMANHÃ]"

        else:

            when = ""

        pace = ""

        if session.target_pace_min and session.target_pace_max:

            pace = f" — pace {session.target_pace_min}-{session.target_pace_max} min/km"

        adjustment = ""

        if session.adjusted and session.adjustment_reason:

            adjustment = f" [AJUSTADO: {session.adjustment_reason}]"

        # tamanho: km OU minutos (treino POR TEMPO) — sem isto a sessão por
        # tempo aparecia como "(0.0 km)" nesta linha (bug do treino por tempo)
        if session.planned_distance_km:

            size = f"{session.planned_distance_km:.1f} km"

        elif session.planned_duration_minutes:

            size = f"{session.planned_duration_minutes} min"

        else:

            size = "—"

        return (
            f"{weekday_label(session.day)} "
            f"({session_date.strftime('%d/%m')}){when} — "
            f"{session.workout_type} "
            f"({size}) — "
            f"{session.objective}{pace}{adjustment}"
        )
