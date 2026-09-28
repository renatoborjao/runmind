from datetime import date, timedelta

from app.application.planner.pace_formatter import PaceFormatter
from app.core.weekdays import weekday_label, weekday_name
from app.domain.entities.adherence_report import AdherenceReport
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan

_RUNNING_KINDS = {"run", "walk", "run_walk"}


class PlanContextBuilder:
    """A parte do contexto que é SÓ da tarefa de montar a semana: qual semana,
    os dias dele (e a regra de agendar neles), o iniciante run/walk, o plano da
    semana passada + o que ele executou dela e os tipos recentes (pra variar).
    Todo o resto — meta, capacidade, evolução, corpo, percepção, padrões,
    memória — vem do DOSSIÊ do atleta, a mesma base de todas as vozes do coach
    ([[AthleteDossier]]). Só fatos — nada inventado."""

    @staticmethod
    def build(
        runner: RunnerProfile,
        goal: TrainingGoal,
        week_start: date,
        days_to_race: int | None = None,
        run_walk: bool = False,
        last_plan: TrainingPlan | None = None,
        recent_plans: list[TrainingPlan] | None = None,
        executed: str = "",
        dossier: str = "",
        today: date | None = None,
        block: str = "",
        request: str = "",
    ) -> str:

        week_end = week_start + timedelta(days=6)

        target = (
            f"SEMANA A MONTAR: {week_start.strftime('%d/%m')} a "
            f"{week_end.strftime('%d/%m/%Y')}."
        )

        if days_to_race is not None and goal is not None and goal.race_date:

            target += (
                f" A prova-âncora ({goal.race_label}) fica a {days_to_race} "
                "dias do início dela."
            )

        lines = [target]

        if block:

            lines.append(block)

        # O PEDIDO que fez o atleta pedir pra refazer a semana ("tô gripado,
        # só leve até sexta"). O dossiê não tem a mensagem atual — sem isto a IA
        # refazia a semana sem saber o que ele pediu (lab 28/09, Maurício).
        if request.strip():

            lines.append(
                "PEDIDO DO ATLETA AGORA — é POR ISSO que você está refazendo a "
                f"semana: {request.strip()}. Honre o pedido nos dias que ele "
                "cobre (a dose e a forma são suas, com o quadro inteiro); o que "
                "ele não citou segue o seu critério."
            )

        # REFAZENDO a semana que já começou (o atleta mudou meta/dias e pediu o
        # plano novo): os dias anteriores ficam como estão
        if today is not None and week_start < today <= week_end:

            lines.append(
                f"A SEMANA JÁ COMEÇOU: hoje é {weekday_label(weekday_name(today))} "
                f"({today.strftime('%d/%m')}). Os dias ANTERIORES a hoje ficam "
                "como estão (o que ele fez está no plano da semana, no dossiê) — "
                "monte as sessões SÓ de hoje em diante, nos dias dele que ainda "
                "vêm, com a dose coerente com o que ele já correu nesta semana."
            )

        # iniciante que começa correndo-caminhando: os dados do onboarding
        # (peso/altura/capacidade) guiam a IA a montar caminhada + run/walk
        if run_walk:

            lines.append(PlanContextBuilder._beginner_line(runner))

        days = ", ".join(
            weekday_label(day) for day in runner.preferred_running_days
        )

        lines.append(
            f"Dias de corrida dele: {days} "
            f"({len(runner.preferred_running_days)}x/semana) — AGENDE as "
            "sessões NESSES dias e mantenha ESSA quantidade (ver REGRAS: não "
            "invente outros dias nem some/tire sessões; só mova o dia de uma "
            "sessão por preferência dele — ex.: longão no domingo — ou por "
            "padrão de furo, nunca por conta própria)."
        )

        # a preferência de DIA do longão não é campo rígido: vive na memória
        # evolutiva (no dossiê) como qualquer outra preferência dinâmica. Ver
        # [[project_longao_dinamico]].

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

        if dossier:

            lines.append("")

            lines.append(dossier)

        return "\n".join(line for line in lines if line is not None)

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
    def _goal_line(
        goal: TrainingGoal,
        weeks_to_race: int | None,
        days_to_race: int | None = None,
    ) -> str:

        if goal.race_date is None:

            pace = PlanContextBuilder._goal_pace(goal)

            # meta com TEMPO sem prova ("5 km em 23 min"): o alvo e o ritmo
            # dele vão explícitos, senão a IA mira no escuro
            target = (
                f" — alvo {goal.target_time} nos {goal.distance_km:g} km "
                f"(~{pace}/km)"
                if goal.target_time and pace
                else ""
            )

            return f"Objetivo do atleta: {goal.name}{target} (sem prova marcada)."

        pace = PlanContextBuilder._goal_pace(goal)

        target = (
            f", alvo {goal.target_time} (~{pace}/km — use pra os tiros no "
            f"ritmo-alvo e o SIMULADO)"
            if goal.target_time and pace
            else (f", alvo {goal.target_time}" if goal.target_time else "")
        )

        # contador em DIAS (preciso): perto da prova, o piso de semanas engana
        # (13 dias virava "1 semana" e o coach afiava cedo). Semanas só como
        # referência grosseira quando ainda falta muito.
        if days_to_race is not None:

            race = f" (faltam {days_to_race} dias)"

        elif weeks_to_race is not None:

            race = f" ({weeks_to_race} semanas até ela)"

        else:

            race = ""

        # separa o OBJETIVO de fundo (aspiração, ex.: 21km/saúde, sem data) da
        # PROVA-âncora concreta (ex.: 10k em 23/08) — periodize PRA A PROVA, mas
        # sem confundir a distância dela com a meta de fundo. Bug do Renato: a
        # prova de 10k virava "meta de 21km em 2 semanas".
        return (
            f"Objetivo de fundo do atleta: {goal.name}.\n"
            f"Prova-âncora (periodize pra ela): {goal.race_label} em "
            f"{goal.race_date.strftime('%d/%m/%Y')}{target}{race}."
        )

    @staticmethod
    def _goal_pace(goal: TrainingGoal) -> str | None:
        """Pace-alvo da prova (mm:ss/km) derivado do tempo-alvo — o número
        exato pra o coach ancorar os tiros no ritmo-alvo E o simulado, sem
        chutar. None sem tempo-alvo/distância."""

        secs = PlanContextBuilder._time_to_seconds(goal.target_time)

        if secs is None or not goal.distance_km:

            return None

        return PaceFormatter.format((secs / 60) / goal.distance_km)

    @staticmethod
    def _time_to_seconds(clock: str | None) -> int | None:
        """"HH:MM:SS" ou "MM:SS" -> segundos. None se não parsear."""

        if not clock:

            return None

        parts = clock.split(":")

        try:

            nums = [int(p) for p in parts]

        except ValueError:

            return None

        if len(nums) == 3:

            return nums[0] * 3600 + nums[1] * 60 + nums[2]

        if len(nums) == 2:

            return nums[0] * 60 + nums[1]

        return None

    @staticmethod
    def _paces_line(metrics: RunnerMetrics) -> str:

        return (
            "Paces reais (min/km): "
            f"fácil {PaceFormatter.format(metrics.easy_pace_min)}–"
            f"{PaceFormatter.format(metrics.easy_pace_max)}, "
            f"limiar {PaceFormatter.format(metrics.threshold_pace)}, "
            f"VO2 {PaceFormatter.format(metrics.vo2_pace)}."
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
                f"{weekday_label(report.missed_day.label)} "
                f"({report.missed_day.count} de "
                f"{report.missed_day.opportunities} vezes que foi prescrita)"
            )

        if report.missed_type:

            parts.append(
                f"treino de {report.missed_type.label} "
                f"({report.missed_type.count} de "
                f"{report.missed_type.opportunities})"
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
            f"{weekday_label(s.day)} {s.workout_type}"
            + (
                f" {s.planned_distance_km:.0f}km"
                if s.planned_distance_km
                else ""
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

            sessions = [
                f"{weekday_label(session.day)[:3]} {session.workout_type}"
                for session in plan.sessions
                if session.kind in _RUNNING_KINDS and session.workout_type
            ]

            if sessions:

                label = plan.week_start.strftime("%d/%m")

                weeks.append(f"{label}: {' · '.join(sessions)}")

        if not weeks:

            return ""

        return (
            "AS ÚLTIMAS SEMANAS, dia a dia — "
            + " | ".join(weeks)
            + ". Olhe a SEMANA INTEIRA, não só o dia forte: se a FORMA se repete "
            "(o leve sempre igual, o longão sempre igual, o forte só trocando de "
            "nome), ela parou de trazer estímulo novo. A escolha é LIVRE — "
            "qualquer treino do repertório ou fora dele, em QUALQUER dia (o "
            "leve e o longão também mudam de forma) — desde que sirva à "
            "evolução dele rumo à meta, no momento do corpo. Uma preferência de "
            "'dia de qualidade' fixa o DIA, não o TIPO."
        )
