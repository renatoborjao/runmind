from datetime import date

from app.application.coach.writer.labels import plan_workout_label
from app.core.clock import today_local
from app.core.weekdays import weekday_label, weekday_name
from app.domain.entities.training_plan import TrainingPlan

# emoji por intensidade do treino
TYPE_EMOJI = {
    "EASY": "🟢",
    "PROGRESSION": "🟡",
    "VO2": "🔴",
    "LONG_RUN": "🔵",
}

# nome da fase do ciclo em pt-BR (ancorada na prova)
PHASE_LABELS = {
    "BASE": "Base",
    "BUILD": "Construção",
    "PEAK": "Pico",
    "TAPER": "Polimento",
}


class WeeklyPlanMessageFormatter:

    @staticmethod
    def format(
        runner_name: str,
        plan: TrainingPlan,
    ) -> str:

        lines = [
            "🏃 RunMind — Plano da semana",
            "",
            f"Bom domingo, {runner_name}! Aqui está seu plano "
            f"pra semana de {plan.week_start.strftime('%d/%m')}:",
            "",
        ]

        lines.extend(WeeklyPlanMessageFormatter._phase_lines(plan))

        lines.extend(
            WeeklyPlanMessageFormatter.session_lines(plan)
        )

        lines.append("Bora treinar! 💪")

        return "\n".join(lines)

    @staticmethod
    def _phase_lines(
        plan: TrainingPlan,
    ) -> list[str]:
        """Cabeçalho da periodização: fase do ciclo e aviso de semana de
        corte. Plano externo (treinador) não tem fase do RunMind."""

        if plan.source == "externo":

            return []

        lines = []

        label = PHASE_LABELS.get(plan.phase)

        if label:

            lines.append(f"📈 Fase: {label}")

        if plan.is_deload:

            lines.append(
                "🔽 Semana de recuperação — volume reduzido de "
                "propósito pra assimilar a carga."
            )

        if lines:

            lines.append("")

        return lines

    @staticmethod
    def week_plan_message(
        runner_name: str,
        plan: TrainingPlan,
        reference_date: date | None = None,
    ) -> str:
        """Plano completo da semana, sob demanda ("qual meu plano?").
        Marca os treinos já passados com ✅ para não parecer que ainda
        estão por fazer — datas sempre honestas."""

        reference_date = reference_date or today_local()

        if not plan.sessions:

            return (
                f"🏃 {runner_name}, ainda não há um plano montado pra "
                f"esta semana. Assim que fechar, te aviso! 💪"
            )

        lines = [f"🏃 Seu plano da semana, {runner_name}:", ""]

        lines.extend(WeeklyPlanMessageFormatter._phase_lines(plan))

        lines.extend(
            WeeklyPlanMessageFormatter.session_lines(
                plan,
                reference_date,
            )
        )

        return "\n".join(lines).strip()

    @staticmethod
    def next_session_message(
        runner_name: str,
        plan: TrainingPlan,
        reference_date: date | None = None,
    ) -> str:
        """Próximo treino (a partir de hoje, incluindo hoje) já com o
        detalhe de execução. Semana concluída vira mensagem de descanso."""

        reference_date = reference_date or today_local()

        session = WeeklyPlanMessageFormatter._next_session(
            plan,
            reference_date,
        )

        if session is None:

            return (
                f"🏃 {runner_name}, você já fechou os treinos desta "
                f"semana! 🎉\n\nSeu novo plano chega no domingo. "
                f"Aproveite pra descansar. 💪"
            )

        return WeeklyPlanMessageFormatter._single_session_message(
            f"🏃 Seu próximo treino, {runner_name}:",
            plan,
            session,
        )

    @staticmethod
    def today_session_message(
        runner_name: str,
        plan: TrainingPlan,
        reference_date: date | None = None,
    ) -> str | None:
        """Treino de HOJE detalhado — ou None se hoje é dia de descanso
        (usado pelo lembrete matinal, que aí não envia nada)."""

        reference_date = reference_date or today_local()

        session = plan.find_session_by_day(
            weekday_name(reference_date),
        )

        if session is None:

            return None

        return WeeklyPlanMessageFormatter._single_session_message(
            f"🏃 Bom dia, {runner_name}! Hoje é dia de treino 🌅",
            plan,
            session,
        )

    @staticmethod
    def _single_session_message(
        intro: str,
        plan: TrainingPlan,
        session,
    ) -> str:

        lines = [intro, ""]

        lines.extend(
            WeeklyPlanMessageFormatter._session_block(plan, session)
        )

        return "\n".join(lines).strip()

    @staticmethod
    def _next_session(
        plan: TrainingPlan,
        reference_date: date,
    ):
        """Sessão mais próxima com data >= referência (hoje incluído)."""

        upcoming = sorted(
            plan.sessions,
            key=lambda session: plan.session_date(session),
        )

        return next(
            (
                session
                for session in upcoming
                if plan.session_date(session) >= reference_date
            ),
            None,
        )

    @staticmethod
    def session_lines(
        plan: TrainingPlan,
        reference_date: date | None = None,
        past_label: str = "✅ (já feito)",
    ) -> list[str]:
        """Blocos detalhados por sessão, em ordem cronológica — reusado
        pelo resumo, onboarding e plano externo. Com `reference_date`,
        sessões já passadas viram uma linha marcada com `past_label`
        (padrão "✅ já feito"; onboarding usa "já passou")."""

        sessions = sorted(
            plan.sessions,
            key=lambda session: plan.session_date(session),
        )

        lines: list[str] = []

        for session in sessions:

            lines.extend(
                WeeklyPlanMessageFormatter._session_block(
                    plan,
                    session,
                    reference_date,
                    past_label,
                )
            )

            lines.append("")

        return lines

    @staticmethod
    def _session_block(
        plan: TrainingPlan,
        session,
        reference_date: date | None = None,
        past_label: str = "✅ (já feito)",
    ) -> list[str]:

        session_date_obj = plan.session_date(session)

        session_date = session_date_obj.strftime("%d/%m")

        code = session.workout_type

        distance = session.planned_distance_km or 0

        emoji = TYPE_EMOJI.get(code, "•")

        label = plan_workout_label(code, distance)

        header = (
            f"{emoji} {weekday_label(session.day)} ({session_date}) — "
            f"{label} · {distance:.1f} km"
        )

        # Sessão já passou: uma linha marcada, sem detalhe de execução —
        # não faz sentido "como executar" um treino que já foi.
        if (
            reference_date is not None
            and session_date_obj < reference_date
        ):

            return [f"{header} {past_label}"]

        detail = WeeklyPlanMessageFormatter._execution_detail(
            code,
            session,
        )

        block = [header]

        block += [f"   • {item}" for item in detail]

        if session.adjusted and session.adjustment_reason:

            block.append(f"   ⚠️ {session.adjustment_reason}")

        return block

    @staticmethod
    def _execution_detail(
        code: str,
        session,
    ) -> list[str]:

        pace_range = WeeklyPlanMessageFormatter._pace_range(session)

        if code == "EASY":

            return [
                "Aquecimento: já começa no ritmo, corpo relaxado",
                f"Execução: {(session.planned_distance_km or 0):.1f} km "
                f"confortáveis{pace_range}, dá pra conversar",
                "Foco: base aeróbica, sem forçar",
            ]

        if code == "PROGRESSION":

            return [
                "Aquecimento: primeiros minutos bem leves",
                f"Execução: comece leve e vá acelerando; termine "
                f"forte{pace_range}",
                "Foco: estímulo de ritmo com segurança, sem tiros",
            ]

        if code == "VO2":

            reps = session.notes or "tiros"

            target = (
                f" a {session.target_pace_min}/km"
                if session.target_pace_min
                else ""
            )

            return [
                "Aquecimento: 10 min leve + 3 acelerações curtas",
                f"Série: {reps} forte{target}",
                "Recuperação: 2 min de trote entre os tiros",
                "Desaquecimento: 10 min leve",
            ]

        if code == "LONG_RUN":

            return [
                f"Execução: {(session.planned_distance_km or 0):.1f} km "
                f"em ritmo leve e constante{pace_range}",
                "Foco: resistência — completar bem, hidratando",
                "Dica: se cansar, reduza o ritmo antes de parar",
            ]

        # tipo desconhecido: linha simples
        return [
            f"{(session.planned_distance_km or 0):.1f} km{pace_range}",
        ]

    @staticmethod
    def _pace_range(session) -> str:

        if session.target_pace_min and session.target_pace_max:

            if session.target_pace_min == session.target_pace_max:

                return f" a {session.target_pace_min}/km"

            return (
                f" ({session.target_pace_min}–"
                f"{session.target_pace_max}/km)"
            )

        return ""
