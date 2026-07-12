from datetime import date

from app.application.coach.writer.labels import plan_workout_label
from app.core.clock import today_local
from app.core.weekdays import weekday_label
from app.domain.entities.training_plan import TrainingPlan

# emoji por intensidade do treino
TYPE_EMOJI = {
    "RECOVERY": "⚪",
    "EASY": "🟢",
    "PROGRESSION": "🟡",
    "FARTLEK": "🟣",
    "TEMPO": "🟠",
    "VO2": "🔴",
    "LONG_RUN": "🔵",
    "WALK": "🚶",
    "RUN_WALK": "🔁",
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

        if plan.weekly_objective:

            lines.append(f"🎯 {plan.weekly_objective}")

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
        done_days: set[str] | None = None,
    ) -> str:
        """Plano completo da semana, sob demanda ("qual meu plano?"). Com
        `done_days` (dias cumpridos, validados no histórico do Strava), os
        treinos passados aparecem como ✅ feito ou ❌ não feito."""

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
                done_days=done_days,
            )
        )

        return "\n".join(lines).strip()

    @staticmethod
    def next_session_message(
        runner_name: str,
        plan: TrainingPlan,
        reference_date: date | None = None,
        done_days: set[str] | None = None,
    ) -> str:
        """Próximo treino (a partir de hoje, incluindo hoje) já com o
        detalhe de execução. Semana concluída vira mensagem de descanso.
        `done_days` pula sessões já cumpridas (mesmo fora de ordem)."""

        reference_date = reference_date or today_local()

        session = WeeklyPlanMessageFormatter._next_session(
            plan,
            reference_date,
            done_days,
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
        (usado pelo lembrete matinal, que aí não envia nada). Casa pela
        DATA real da sessão, NÃO pelo nome do dia: um plano de outra semana
        (ex.: o da semana que vem, já gerado no domingo) jamais vira "treino
        de hoje" só porque cai no mesmo dia da semana."""

        reference_date = reference_date or today_local()

        session = next(
            (
                session
                for session in plan.sessions
                if plan.session_date(session) == reference_date
            ),
            None,
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
        done_days: set[str] | None = None,
    ):
        """Sessão mais próxima com data >= referência (hoje incluído),
        pulando as já cumpridas (`done_days`)."""

        done = {day.lower() for day in (done_days or set())}

        upcoming = sorted(
            plan.sessions,
            key=lambda session: plan.session_date(session),
        )

        return next(
            (
                session
                for session in upcoming
                if plan.session_date(session) >= reference_date
                and session.day.lower() not in done
            ),
            None,
        )

    @staticmethod
    def session_lines(
        plan: TrainingPlan,
        reference_date: date | None = None,
        past_label: str = "✅ (já feito)",
        done_days: set[str] | None = None,
    ) -> list[str]:
        """Blocos detalhados por sessão, em ordem cronológica — reusado
        pelo resumo, onboarding e plano externo. Com `reference_date`,
        sessões já passadas viram uma linha marcada. Se `done_days` for
        dado, marca ✅ feito / ❌ não feito validando o histórico; senão
        usa `past_label` fixo (onboarding: "já passou")."""

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
                    done_days,
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
        done_days: set[str] | None = None,
    ) -> list[str]:

        session_date_obj = plan.session_date(session)

        session_date = session_date_obj.strftime("%d/%m")

        code = session.workout_type

        distance = session.planned_distance_km or 0

        # tipo conhecido tem emoji por intensidade; plano externo (treinador)
        # usa um marcador de dia neutro
        emoji = TYPE_EMOJI.get(code, "🔹")

        label = plan_workout_label(code, distance)

        # run/walk e caminhada são medidos em tempo; corrida, em km
        if session.planned_distance_km:

            size = f" · {session.planned_distance_km:.1f} km"

        elif session.planned_duration_minutes:

            size = f" · {session.planned_duration_minutes} min"

        else:

            size = ""

        header = (
            f"{emoji} {weekday_label(session.day)} ({session_date}) — "
            f"{label}{size}"
        )

        # Sessão já passou: uma linha marcada, sem detalhe de execução —
        # não faz sentido "como executar" um treino que já foi.
        if (
            reference_date is not None
            and session_date_obj < reference_date
        ):

            if done_days is not None:

                mark = (
                    "✅ (feito)"
                    if session.day in done_days
                    else "❌ (não feito)"
                )

            else:

                mark = past_label

            return [f"{header} {mark}"]

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

        # Plano da IA-treinadora: a própria sessão traz a estrutura (um
        # passo por linha) e o propósito prontos — renderiza cada passo.
        if getattr(session, "structure", ""):

            detail = [
                step
                for step in session.structure.split("\n")
                if step.strip()
            ]

            if session.purpose:

                detail.append(f"Foco: {session.purpose}")

            return detail

        pace_range = WeeklyPlanMessageFormatter._pace_range(session)

        if code == "WALK":

            pace = (
                f" (~{session.target_pace_min}/km)"
                if session.target_pace_min
                else ""
            )

            return [
                "Aquecimento: comece devagar nos primeiros minutos",
                f"Execução: {session.planned_duration_minutes} min de "
                f"caminhada em ritmo confortável{pace}, respiração "
                f"tranquila e postura ereta",
                "Foco: criar o hábito e a base aeróbica, sem pressa",
                "Dica: se sobrar fôlego, pode apertar o passo no fim",
            ]

        if code == "RUN_WALK":

            return WeeklyPlanMessageFormatter._run_walk_detail(session)

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

        if code == "TEMPO":

            return [
                "Aquecimento: 10 min leve",
                f"Execução: trecho contínuo em ritmo forte porém "
                f"sustentável{pace_range}",
                "Foco: limiar — segurar o ritmo sem estourar",
                "Desaquecimento: 10 min leve",
            ]

        if code == "FARTLEK":

            return [
                "Aquecimento: 10 min leve",
                f"Execução: jogo de velocidades — alterne trechos "
                f"fortes e leves à vontade{pace_range}",
                "Foco: ritmo de prova de forma lúdica, sem cronômetro",
                "Desaquecimento: 5–10 min leve",
            ]

        if code == "RECOVERY":

            return [
                f"Execução: {(session.planned_distance_km or 0):.1f} km "
                f"bem leves{pace_range}",
                "Foco: soltar as pernas e acelerar a recuperação",
                "Dica: se estiver cansado, pode virar caminhada",
            ]

        # tipo desconhecido (ex.: plano externo do treinador): o texto do
        # treinador (objetivo + observações) costuma vir com várias linhas —
        # renderiza CADA linha como um item limpo (sem "•/-" crus embutidos e
        # sem repetir a distância, que já está no cabeçalho).
        detail: list[str] = []

        for block in (
            getattr(session, "objective", "") or "",
            getattr(session, "notes", "") or "",
        ):

            for raw_line in block.split("\n"):

                line = raw_line.strip().lstrip("•-*·").strip()

                if not line or line == code or line in detail:

                    continue

                detail.append(line)

        return detail

    @staticmethod
    def _run_walk_detail(session) -> list[str]:

        iv = session.intervals or {}

        warmup = iv.get("warmup_min", 5)

        cooldown = iv.get("cooldown_min", 5)

        reps = iv.get("reps", 0)

        trot = WeeklyPlanMessageFormatter._duration(iv.get("trot_sec", 0))

        walk = WeeklyPlanMessageFormatter._duration(iv.get("walk_sec", 0))

        trot_pace = (
            f" (~{session.target_pace_min}/km)"
            if session.target_pace_min
            else ""
        )

        return [
            f"Aquecimento: {warmup} min de caminhada leve",
            f"Série: {reps}x (trote {trot}{trot_pace} + caminhada {walk})",
            "Foco: alternar sem forçar — se cansar, é só caminhar mais",
            f"Desaquecimento: {cooldown} min de caminhada",
        ]

    @staticmethod
    def _duration(seconds: int) -> str:
        """Segundos -> texto curto: 60->'1 min', 30->'30s', 90->'1min30'."""

        seconds = int(seconds)

        if seconds < 60:

            return f"{seconds}s"

        minutes, rest = divmod(seconds, 60)

        if rest == 0:

            return f"{minutes} min"

        return f"{minutes}min{rest:02d}"

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
