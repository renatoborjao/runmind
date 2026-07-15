from __future__ import annotations

from datetime import date

from app.application.planner.pace_formatter import PaceFormatter

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
            "🏃 RunMind — Resumo da semana",
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
            WeeklyReviewMessageFormatter._pace_line(current, previous)
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

        lines.append(
            "Semana que vem tem plano novo chegando. Bora! 💪"
        )

        return "\n".join(lines)

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
    ) -> str:

        return (
            f"• Pace médio: "
            f"{WeeklyReviewMessageFormatter._pace(current['avg_pace_min_km'])} "
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
    def _goal_lines(goal: dict) -> list[str]:
        """Seção do objetivo — adapta ao atleta: prova/marca com data vira
        contagem regressiva; sem prova (saúde/evolução) só ecoa o objetivo,
        sem cobrança de tempo."""

        name = goal.get("name")

        if not name:

            return []

        if goal.get("has_race"):

            weeks = goal.get("weeks_to_race")

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

            return ["🎯 Rumo à meta", f"• {name}{faltam}{target}"]

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
