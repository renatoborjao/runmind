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
            f"Fala, {runner_name}! Fechando a semana de {week_start}:",
            "",
            "📊 Esta semana vs. anterior",
            WeeklyReviewMessageFormatter._volume_line(
                current,
                previous,
                comparison["delta"],
            ),
            f"• Treinos: {current['runs']} ({previous['runs']} na anterior)",
            WeeklyReviewMessageFormatter._pace_line(
                current,
                previous,
            ),
        ]

        trend_lines = WeeklyReviewMessageFormatter._trend_lines(
            review["trends"],
        )

        if trend_lines:

            lines.append("")

            lines.append(
                "📈 Tendência (últimas 4 semanas vs. 4 anteriores)"
            )

            lines.extend(trend_lines)

        lines.append("")

        lines.append(
            f"Consistência nas últimas semanas: "
            f"{review['consistency']:.1f}%"
        )

        lines.append("")

        lines.append(
            "Semana que vem tem plano novo chegando. Bora! 💪"
        )

        return "\n".join(lines)

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
    def _trend_lines(
        trends: dict,
    ) -> list[str]:

        lines = []

        volume = trends["volume"]

        if volume["delta_percent"] is not None:

            lines.append(
                f"• Volume: {VOLUME_DIRECTIONS[volume['direction']]} "
                f"({volume['delta_percent']:+.1f}%)"
            )

        pace = trends["pace"]

        if pace["delta_percent"] is not None:

            lines.append(
                f"• Pace: {PACE_DIRECTIONS[pace['direction']]} "
                f"({pace['delta_percent']:+.1f}%)"
            )

        return lines
