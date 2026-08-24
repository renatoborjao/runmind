from __future__ import annotations

from datetime import date

from app.application.history.streak_calculator import StreakCalculator
from app.application.planner.pace_formatter import PaceFormatter
from app.application.review.predicted_time_line_formatter import (
    PredictedTimeLineFormatter,
)
from app.core.weekdays import weekday_label
from app.domain.entities.adherence_report import (
    ADHERENCE_FALLING,
    ADHERENCE_RISING,
    AdherenceReport,
)

# quantas semanas da série cabem na mensagem sem virar parede de números
ADHERENCE_DISPLAY_WEEKS = 4

VOLUME_DIRECTIONS = {
    "up": "subindo",
    "down": "caindo",
    "stable": "estável",
}

# Pace menor é melhor: "down" significa que o corredor está mais rápido.
PACE_DIRECTIONS = {
    "up": "mais lento",
    "down": "mais rápido",
    "stable": "estável",
}


class WeeklyReviewMessageFormatter:

    @staticmethod
    def format(
        runner_name: str,
        review: dict,
        narrative: list[str] | None = None,
    ) -> str | None:

        comparison = review["comparison"]

        current = comparison["current_week"]

        previous = comparison["previous_week"]

        # duas semanas zeradas: nada a resumir
        if current["runs"] == 0 and previous["runs"] == 0:

            return None

        week_start = date.fromisoformat(
            review["week_start"]
        ).strftime("%d/%m")

        lines = [
            "🏃 Ritmind — Resumo da semana",
            "",
            f"Fala, {runner_name}! Fechando a semana de {week_start}.",
            "",
            "📝 Como foi sua semana",
        ]

        # narrativa da IA (voz de treinador, guiada pelo objetivo) ou fallback
        lines.extend(
            narrative
            or WeeklyReviewMessageFormatter._fallback_narrative(review)
        )

        # a PROVA da semana é o destaque — garante o reconhecimento mesmo se a
        # narrativa da IA cair no fallback (era a queixa do Renato: resumo da
        # semana da prova sem falar UMA palavra da prova)
        race = review.get("race")

        if race:

            lines.append("")

            lines.append(WeeklyReviewMessageFormatter._race_highlight(race))

        lines.append("")

        lines.append("📊 Números (esta vs. anterior)")

        lines.append(
            WeeklyReviewMessageFormatter._volume_line(
                current,
                previous,
                comparison["delta"],
            )
        )

        lines.append(
            WeeklyReviewMessageFormatter._workouts_line(
                current,
                previous,
                review.get("adherence"),
            )
        )

        lines.append(
            WeeklyReviewMessageFormatter._pace_line(
                current, previous, race=review.get("race"),
            )
        )

        if review.get("longest_km"):

            lines.append(
                f"• Longão da semana: {review['longest_km']:.1f} km"
            )

        trend_lines = WeeklyReviewMessageFormatter._trend_lines(
            review.get("trends") or {},
        )

        if trend_lines:

            lines.append("")

            lines.append(
                "📈 Evolução (últimas 4 semanas vs. 4 anteriores)"
            )

            lines.extend(trend_lines)

        adherence_lines = WeeklyReviewMessageFormatter._adherence_lines(
            review.get("adherence_history"),
        )

        if adherence_lines:

            lines.append("")

            lines.append("🧭 Aderência ao plano")

            lines.extend(adherence_lines)

        goal_lines = WeeklyReviewMessageFormatter._goal_lines(
            review.get("goal") or {},
        )

        if goal_lines:

            lines.append("")

            lines.extend(goal_lines)

        lines.append("")

        lines.append(
            f"🔥 Consistência nas últimas semanas: "
            f"{review['consistency']:.0f}%"
        )

        lines.append("")

        # o plano da próxima sai HOJE, logo depois do resumo (não "semana que
        # vem" — era a queixa do Renato, que recebeu isto no MESMO dia do plano)
        if review.get("plan_incoming", True):

            lines.append(
                "Teu plano da próxima semana chega já já. Bora! 💪"
            )

        else:

            lines.append(
                "Segue firme na próxima — bora! 💪"
            )

        return "\n".join(lines)

    @staticmethod
    def _race_highlight(race: dict) -> str:
        """A linha de destaque da PROVA da semana — o dia mais importante não
        pode passar em branco no resumo."""

        label = race.get("race_label") or "prova"

        time = race.get("time")

        target = race.get("target_time")

        beat = race.get("beat")

        if beat is True and target:

            return (
                f"🏁 PROVA da semana: {label} em {time} — "
                f"você BATEU a meta de {target}! 🏆"
            )

        if beat is False and target:

            return f"🏁 PROVA da semana: {label} em {time} (meta era {target})."

        return f"🏁 PROVA da semana: {label} em {time} — concluída! 🎉"

    @staticmethod
    def _fallback_narrative(review: dict) -> list[str]:
        """Sem a IA: uma frase honesta com os números, nunca silêncio."""

        current = review["comparison"]["current_week"]

        return [
            f"Você fechou a semana com {current['runs']} treino(s) e "
            f"{current['distance_km']:.1f} km. Segue firme na rotina! 👊"
        ]

    @staticmethod
    def _volume_line(
        current: dict,
        previous: dict,
        delta: dict,
    ) -> str:

        percent = ""

        if delta["volume_delta_percent"] is not None:

            percent = f", {delta['volume_delta_percent']:+.1f}%"

        return (
            f"• Volume: {current['distance_km']:.1f} km "
            f"({previous['distance_km']:.1f} km na anterior{percent})"
        )

    @staticmethod
    def _workouts_line(
        current: dict,
        previous: dict,
        adherence: dict | None,
    ) -> str:
        """Com o plano da semana: mostra a ADERÊNCIA (X de Y cumpridos). Sem
        plano identificado: cai na contagem simples de treinos."""

        if adherence:

            return (
                f"• Treinos do plano: {adherence['done']} de "
                f"{adherence['planned']} ✅"
            )

        return (
            f"• Treinos: {current['runs']} "
            f"({previous['runs']} na anterior)"
        )

    @staticmethod
    def _pace_line(
        current: dict,
        previous: dict,
        race: dict | None = None,
    ) -> str:
        """Pace médio da semana. Se houve PROVA na semana, o médio vem PUXADO
        pelo esforço máximo dela — marca isso pra não ler como pace de treino
        (honestidade; era a dúvida do Renato)."""

        note = " (inclui a prova)" if race else ""

        return (
            f"• Pace médio: "
            f"{WeeklyReviewMessageFormatter._pace(current['avg_pace_min_km'])}"
            f"{note} "
            f"({WeeklyReviewMessageFormatter._pace(previous['avg_pace_min_km'])} "
            f"na anterior)"
        )

    @staticmethod
    def _pace(
        pace_min_km: float | None,
    ) -> str:

        if pace_min_km is None:

            return "—"

        return f"{PaceFormatter.format(pace_min_km)} min/km"

    @staticmethod
    def _adherence_lines(
        report: AdherenceReport | None,
    ) -> list[str]:
        """Como o cumprimento do plano vem se comportando ao longo das
        semanas, e o que mais fica pra trás. Só aparece com 2+ semanas de
        plano — com uma só, a linha "Treinos do plano" acima já diz tudo.
        O padrão (dia/tipo) já vem filtrado pelo analyzer: se está aqui, é
        porque repete, não foi um tropeço isolado."""

        if report is None or not report.has_series:

            return []

        lines: list[str] = []

        # sequência de consistência (só quando há 2+ semanas seguidas cumpridas)
        # — reforço positivo; quebra nunca vira cobrança aqui
        streak = StreakCalculator.consecutive_weeks(report.weeks)

        if streak >= 2:

            fire = "🔥🔥" if streak >= 4 else "🔥"

            lines.append(
                f"{fire} {streak} semanas SEGUIDAS cumprindo o plano — é essa "
                "consistência que constrói de verdade!"
            )

        shown = report.weeks[-ADHERENCE_DISPLAY_WEEKS:]

        series = " · ".join(f"{week.done}/{week.planned}" for week in shown)

        planned = sum(week.planned for week in shown)

        done = sum(week.done for week in shown)

        rate = f" ({done / planned * 100:.0f}%)" if planned else ""

        lines.append(f"• Últimas {len(shown)} semanas: {series}{rate}")

        # "vem cumprindo MAIS" só faz sentido se a série EXIBIDA sobe de verdade.
        # Quando as semanas mostradas estão no teto (todas cumpridas) ou iguais,
        # dizer "mais que antes" contradiz o que o atleta vê (3/3·3/3·3/3·3/3) —
        # a linha do streak acima já celebra. Suprime (fim da redundância + do
        # sem-nexo). Bug do Renato.
        shown_perfect = all(
            week.done >= week.planned for week in shown if week.planned
        )

        shown_flat = len({(week.done, week.planned) for week in shown}) == 1

        if report.trend == ADHERENCE_RISING and not (shown_perfect or shown_flat):

            lines.append(
                "• Você vem cumprindo mais que nas semanas anteriores 👏"
            )

        elif report.trend == ADHERENCE_FALLING:

            lines.append(
                "• O cumprimento vem caindo — se a rotina mudou, me conta "
                "que a gente ajusta o plano"
            )

        if report.missed_day:

            day = weekday_label(report.missed_day.label).capitalize()

            lines.append(
                f"• {day} é o dia que mais escapa "
                f"({report.missed_day.count} de "
                f"{report.missed_day.opportunities})"
            )

        if report.missed_type:

            lines.append(
                f"• Treino que mais fica pra trás: "
                f"{report.missed_type.label} "
                f"({report.missed_type.count} de "
                f"{report.missed_type.opportunities})"
            )

        return lines

    @staticmethod
    def _goal_lines(goal: dict) -> list[str]:
        """Seção do objetivo — adapta ao atleta: prova/marca com data vira
        contagem regressiva; sem prova (saúde/evolução) só ecoa o objetivo,
        sem cobrança de tempo."""

        name = goal.get("name")

        if not name:

            return []

        if goal.get("has_race"):

            weeks = goal.get("weeks_to_race")

            # a PROVA pela distância (10k), NUNCA o objetivo de fundo (name):
            # colar "faltam 2 semanas" no 21km sem data era o bug do Renato.
            race_label = goal.get("race_label") or "prova"

            target = (
                f", alvo {goal['target_time']}"
                if goal.get("target_time")
                else ""
            )

            faltam = (
                f" — faltam {weeks} semanas"
                if weeks is not None
                else ""
            )

            lines = ["🎯 Rumo à prova", f"• {race_label}{faltam}{target}"]

            predicted_line = PredictedTimeLineFormatter.line(
                goal.get("predicted_time"),
                goal.get("target_time"),
            )

            if predicted_line:

                lines.append(predicted_line)

            # objetivo de FUNDO (aspiração, SEM contagem) — separado da prova
            lines.append(f"• Objetivo de fundo: {name}")

            return lines

        return ["🎯 Seu objetivo", f"• {name}"]

    @staticmethod
    def _trend_lines(
        trends: dict,
    ) -> list[str]:

        lines = []

        volume = trends.get("volume") or {}

        if volume.get("delta_percent") is not None:

            lines.append(
                f"• Volume: {VOLUME_DIRECTIONS[volume['direction']]} "
                f"({volume['delta_percent']:+.1f}%)"
            )

        pace = trends.get("pace") or {}

        if pace.get("delta_percent") is not None:

            lines.append(
                f"• Pace: {PACE_DIRECTIONS[pace['direction']]} "
                f"({pace['delta_percent']:+.1f}%)"
            )

        return lines
