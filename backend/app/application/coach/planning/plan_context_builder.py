from app.application.planner.pace_formatter import PaceFormatter
from app.core.weekdays import weekday_label
from app.domain.entities.adherence_report import AdherenceReport
from app.domain.entities.runner_baseline import RunnerBaseline
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan

_RUNNING_KINDS = {"run", "walk", "run_walk"}


class PlanContextBuilder:
    """Monta o retrato REAL do atleta que a IA-treinadora lê para gerar o
    plano da semana: meta, dias que ele corre, volume/paces reais,
    execução das últimas semanas, plano anterior e limitações. Só fatos —
    nada inventado."""

    @staticmethod
    def build(
        runner: RunnerProfile,
        goal: TrainingGoal,
        metrics: RunnerMetrics,
        baseline: RunnerBaseline,
        recent_adherence: list[float],
        last_plan: TrainingPlan | None,
        memory: str,
        weeks_to_race: int | None,
        executed: str = "",
        run_walk: bool = False,
        adherence_report: AdherenceReport | None = None,
        learnings: str = "",
        body_directive: str = "",
        fitness_directive: str = "",
        recent_plans: list[TrainingPlan] | None = None,
    ) -> str:

        lines = [f"Atleta: {runner.name}"]

        lines.append(PlanContextBuilder._goal_line(goal, weeks_to_race))

        # iniciante que começa correndo-caminhando: os dados do onboarding
        # (peso/altura/capacidade) guiam a IA a montar caminhada + run/walk
        if run_walk:

            lines.append(PlanContextBuilder._beginner_line(runner))

        days = ", ".join(
            weekday_label(day) for day in runner.preferred_running_days
        )

        lines.append(
            f"Dias de corrida dele: {days} "
            f"({len(runner.preferred_running_days)}x/semana) — respeite "
            "essa frequência."
        )

        # preferência de PADRÃO pro longão — não é regra fixa: algo mais
        # recente (conversa/memória, mudança da semana) pode sobrepor. Tudo
        # aqui é dinâmico e a IA relê fresco a cada geração.
        if runner.preferred_long_run_day:

            lines.append(
                "Por padrão ele faz o longão "
                f"{weekday_label(runner.preferred_long_run_day)} (pode mudar "
                "se algo mais recente na conversa/memória pedir outro dia)."
            )

        lines.append(
            "Volume real: ~%.1f km/sem (última %.1f, melhor %.1f), "
            "tendência %s."
            % (
                baseline.weekly_km,
                baseline.last_week_km,
                baseline.max_week_km,
                baseline.trend,
            )
        )

        lines.append(
            "Rodagem típica ~%.1f km; maior treino ~%.1f km."
            % (baseline.typical_run_km, baseline.longest_km)
        )

        lines.append(PlanContextBuilder._paces_line(metrics))

        lines.append(
            PlanContextBuilder._adherence_line(recent_adherence)
        )

        # o QUE ele vive furando (dia/tipo) — dá à IA a chance de
        # reposicionar em vez de represcrever o treino que nunca acontece
        lines.append(
            PlanContextBuilder._missed_pattern_line(adherence_report)
        )

        if last_plan is not None and last_plan.sessions:

            lines.append(PlanContextBuilder._last_plan_line(last_plan))

        # tipos das últimas semanas — pra a IA VER se está repetindo o mesmo
        # cardápio e VARIAR (periodização). É o sinal que quebra a monotonia.
        if recent_plans:

            line = PlanContextBuilder._recent_types_line(recent_plans)

            if line:

                lines.append(line)

        # o VIVO: o que ele realmente executou (pace/distância por treino)
        if executed:

            lines.append(executed)

        if runner.injuries:

            lines.append(
                "Lesões/limitações: " + ", ".join(runner.injuries) + "."
            )

        if memory:

            lines.append(f"Memória do atleta:\n{memory}")

        # o que o coach APRENDEU observando o comportamento/resultado dele ao
        # longo das semanas (distinto da memória acima, que é o que ele DIZ).
        # Só entra quando a flag de injeção está ligada (o chamador decide).
        if learnings:

            lines.append(learnings)

        # o CORPO agora (carga à luz da recuperação): quando pede freio, entra
        # como diretriz pra a IA decidir a dose — o coach decide, não o atleta.
        if body_directive:

            lines.append(body_directive)

        # a FORMA ao longo das semanas (o atleta está evoluindo?): sobe ->
        # progride; estagnou -> já traz o estímulo que fura o platô; caiu ->
        # alivia. É o loop fechado — o plano se adapta à evolução, não pergunta.
        if fitness_directive:

            lines.append(fitness_directive)

        return "\n".join(line for line in lines if line)

    @staticmethod
    def _beginner_line(runner: RunnerProfile) -> str:

        bmi = (
            runner.weight / (runner.height ** 2)
            if runner.height
            else 0
        )

        mobility = {
            "walker": "hoje só caminha",
            "run_walker": "hoje faz trote e caminhada",
            "runner": "corre pouco, contínuo",
        }.get(runner.mobility, "iniciante absoluto")

        parts = [
            "INICIANTE — começar correndo-caminhando (run/walk): "
            f"{runner.weight:.0f} kg, {runner.height:.2f} m"
        ]

        if bmi:

            parts[0] += f" (IMC {bmi:.0f})"

        parts.append(f"; {mobility}")

        if runner.continuous_run_minutes:

            parts.append(
                f"; corre sem parar ~{runner.continuous_run_minutes:.0f} min"
            )

        if runner.walk_pace_min_km:

            parts.append(
                f"; caminha a "
                f"{PaceFormatter.format(runner.walk_pace_min_km)}/km"
            )

        parts.append(
            ". Monte CAMINHADAS + blocos curtos de trote intercalados com "
            "caminhada (kind 'walk'/'run_walk'), progressão gentil, nunca "
            "além do que ele aguenta. Nada de corrida contínua longa."
        )

        return "".join(parts)

    @staticmethod
    def _goal_line(goal: TrainingGoal, weeks_to_race: int | None) -> str:

        if goal.race_date is None:

            return f"Meta: {goal.name} (sem prova marcada)."

        target = f", alvo {goal.target_time}" if goal.target_time else ""

        race = (
            f" — {weeks_to_race} semanas até a prova"
            if weeks_to_race is not None
            else ""
        )

        return (
            f"Meta: {goal.name} em "
            f"{goal.race_date.strftime('%d/%m/%Y')}{target}{race}."
        )

    @staticmethod
    def _paces_line(metrics: RunnerMetrics) -> str:

        return (
            "Paces reais (min/km): fácil %s–%s, limiar %s, VO2 %s."
            % (
                PaceFormatter.format(metrics.easy_pace_min),
                PaceFormatter.format(metrics.easy_pace_max),
                PaceFormatter.format(metrics.threshold_pace),
                PaceFormatter.format(metrics.vo2_pace),
            )
        )

    @staticmethod
    def _adherence_line(recent_adherence: list[float]) -> str:

        if not recent_adherence:

            return "Execução recente: sem plano anterior registrado."

        pcts = ", ".join(
            f"{round(a * 100)}%" for a in recent_adherence
        )

        return (
            f"Execução das últimas semanas (cumpriu do plano): {pcts} "
            "(da mais antiga p/ a recente) — se vem cumprindo pouco, "
            "segure/recue; se cumpre bem, pode evoluir."
        )

    @staticmethod
    def _missed_pattern_line(
        report: AdherenceReport | None,
    ) -> str:
        """Padrão de furo — só sai quando REPETE (o analyzer já filtra o
        tropeço isolado). Vazio quando não há padrão: string vazia é
        descartada na montagem, então o prompt não ganha ruído."""

        if report is None:

            return ""

        parts = []

        if report.missed_day:

            parts.append(
                "%s (%d de %d vezes que foi prescrita)"
                % (
                    weekday_label(report.missed_day.label),
                    report.missed_day.count,
                    report.missed_day.opportunities,
                )
            )

        if report.missed_type:

            parts.append(
                "treino de %s (%d de %d)"
                % (
                    report.missed_type.label,
                    report.missed_type.count,
                    report.missed_type.opportunities,
                )
            )

        if not parts:

            return ""

        return (
            "O que ele mais deixa pra trás: "
            + "; ".join(parts)
            + ". Não é preguiça — é a rotina dele. Considere mover esse "
            "treino de dia, encurtar ou trocar o formato, em vez de "
            "prescrever de novo igual."
        )

    @staticmethod
    def _last_plan_line(last_plan: TrainingPlan) -> str:

        sessions = "; ".join(
            "%s %s%s"
            % (
                weekday_label(s.day),
                s.workout_type,
                (
                    f" {s.planned_distance_km:.0f}km"
                    if s.planned_distance_km
                    else ""
                ),
            )
            for s in last_plan.sessions
        )

        return f"Plano da semana passada: {sessions}."

    @staticmethod
    def _recent_types_line(recent_plans: list[TrainingPlan]) -> str:
        """Os tipos de treino das últimas semanas, semana a semana — pra a IA
        ENXERGAR se vem repetindo o mesmo cardápio e variar o estímulo."""

        weeks = []

        for plan in recent_plans:

            types = [
                session.workout_type
                for session in plan.sessions
                if session.kind in _RUNNING_KINDS and session.workout_type
            ]

            if types:

                label = plan.week_start.strftime("%d/%m")

                weeks.append(f"{label}: {', '.join(types)}")

        if not weeks:

            return ""

        return (
            "Tipos de treino das últimas semanas — "
            + " | ".join(weeks)
            + ". IMPORTANTE: se os tipos vêm SE REPETINDO, VARIE agora (traga "
            "tempo/limiar, fartlek ou progressivo que sirva à fase/meta) em "
            "vez de repetir o mesmo cardápio."
        )
