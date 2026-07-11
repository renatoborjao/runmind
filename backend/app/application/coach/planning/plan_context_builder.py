from app.application.planner.pace_formatter import PaceFormatter
from app.core.weekdays import weekday_label
from app.domain.entities.runner_baseline import RunnerBaseline
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan


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

        if last_plan is not None and last_plan.sessions:

            lines.append(PlanContextBuilder._last_plan_line(last_plan))

        # o VIVO: o que ele realmente executou (pace/distância por treino)
        if executed:

            lines.append(executed)

        if runner.injuries:

            lines.append(
                "Lesões/limitações: " + ", ".join(runner.injuries) + "."
            )

        if memory:

            lines.append(f"Memória do atleta:\n{memory}")

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
