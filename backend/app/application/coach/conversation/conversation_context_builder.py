from datetime import timedelta

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.metrics_resolver import (
    MetricsResolver,
)
from app.application.planner.weekly_plan_matcher import (
    WeeklyPlanMatcher,
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
            f"Último treino: {ConversationContextBuilder._last_activity_summary(history)}\n"
            f"Próximo treino planejado: {ConversationContextBuilder._next_session_summary(plan, history)}\n"
            + ConversationContextBuilder._next_plan_line(runner, plan, today)
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

        # pergunta de esforço em aberto: uma resposta em PALAVRAS ("foi
        # tranquilo") é a resposta a ela — o cérebro grava como percepção
        from app.application.coach.intelligence.perception_recorder import (
            PerceptionRecorder,
        )

        pending_rpe = PerceptionRecorder.pending_line(profile)

        if pending_rpe:

            facts = f"{facts}{pending_rpe}\n"

        # o DOSSIÊ: o quadro INTEIRO do atleta, da MESMA fonte que o plano, a
        # análise e as mensagens do dia leem — um coach, um cérebro. Antes o
        # chat montava o próprio recorte e divergia do plano (varredura 26/09).
        from app.application.coach.context.athlete_dossier import AthleteDossier

        dossier = AthleteDossier.render(
            profile, runner=runner, history=history, plan=plan, today=today,
        )

        if dossier:

            facts = f"{facts}\n{dossier}\n"

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

        # ARMÁRIO DE TÊNIS: sem isto o coach responde sobre calçado no vácuo e
        # INVENTA pares ("Corre 4" que o atleta não tem — bug real do Renato).
        # Só entra quando o assunto é tênis (portão barato), pra o prompt seguir
        # enxuto. Ver [[project_tracker_tenis]] e [[project_consumo_tokens]].
        armario = ConversationContextBuilder._shoe_armario(
            profile,
            incoming_text,
        )

        if armario:

            facts = f"{facts}\n{armario}\n"

        return facts

    @staticmethod
    def _next_plan_line(runner, plan, today) -> str:
        """QUANDO chega o plano da semana que vem — fato do sistema. Sem isto o
        coach inventou "amanhã cedinho o plano entra na tela" num domingo às
        19h (sai às 20h) e ainda disse o que o plano "já entrega" antes de ele
        existir (Renato 27/09). Treinador externo: o plano vem dele."""

        if getattr(runner, "external_coach", False):

            return ""

        from app.application.planner.weekly_plan_notifier import PLAN_HOUR
        from app.core.clock import now_local

        next_monday = today + timedelta(days=7 - today.weekday())

        when = next_monday.strftime("%d/%m")

        if plan is not None and plan.week_start >= next_monday:

            return (
                f"PLANO DA SEMANA QUE VEM ({when}): já montado e enviado — é o "
                "que está no quadro.\n"
            )

        if today.weekday() == 6:

            if now_local().hour < PLAN_HOUR:

                return (
                    f"PLANO DA SEMANA QUE VEM ({when}): sai HOJE às {PLAN_HOUR}h, "
                    "automático, e AINDA NÃO FOI MONTADO — não diga o que ele vai "
                    "ter nem que chega amanhã.\n"
                )

            return (
                f"PLANO DA SEMANA QUE VEM ({when}): sendo montado agora, chega "
                "hoje à noite.\n"
            )

        sunday = next_monday - timedelta(days=1)

        return (
            f"PLANO DA SEMANA QUE VEM ({when}): sai domingo "
            f"({sunday.strftime('%d/%m')}) às {PLAN_HOUR}h, automático.\n"
        )

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

    # rótulo amigável de cada função no grounding do chat
    _SHOE_CATEGORY_PT = {
        "rápido": "rápido (tiros/prova)",
        "versátil": "versátil (serve pra tudo)",
        "dia a dia": "dia a dia (rodagem/longão)",
    }

    _SHOE_KEYWORDS = (
        "tênis", "tenis", "calçado", "calcado", "sapato", "par novo",
        "rodízio", "rodizio", "solado", "amortec",
    )

    @staticmethod
    def _shoe_armario(profile: str, incoming_text: str) -> str:
        """Armário REAL do atleta (pares + função + km) pro coach falar de tênis
        ancorado — nunca inventar modelo. Portão barato: só entra quando a
        mensagem cita tênis ou o nome de um par do armário. Best-effort."""

        try:

            from app.domain.entities.shoe import canonical_category
            from app.infrastructure.persistence.shoe_repository import (
                ShoeRepository,
            )

            active = ShoeRepository().load(profile).active()

            if not active:

                return ""

            text = (incoming_text or "").lower()

            mentions = any(
                kw in text for kw in ConversationContextBuilder._SHOE_KEYWORDS
            ) or any(
                s.name.lower() in text
                or (s.nickname and s.nickname.lower() in text)
                for s in active
            )

            if not mentions:

                return ""

            lines = [
                "ARMÁRIO DE TÊNIS DO ATLETA (estes são os ÚNICOS pares que ele "
                "tem — para falar de tênis use SÓ esta lista; NUNCA invente nem "
                "cite um modelo que não está aqui):"
            ]

            for s in active:

                cat = ConversationContextBuilder._SHOE_CATEGORY_PT.get(
                    canonical_category(s.category), "sem categoria definida"
                )

                default = " [par padrão]" if s.is_default else ""

                lines.append(
                    f"- {s.label}: {cat}{default} — {round(s.total_km)} km"
                )

            return "\n".join(lines)

        except Exception as e:

            print(f"Armário de tênis falhou p/ '{profile}': {e}")

            return ""

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
