"""Monta os números do MÊS que fechou — km, treinos, consistência e os
recordes batidos naquele mês específico (lidos do PersonalRecordRepository,
já datados). Espelha o WeeklyReviewBuilder, mas em janela de mês-calendário
em vez de semana ISO — por isso não reaproveita o ConsistencyCalculator
(pensado pra janela de semanas rolantes, encaixe imperfeito nas bordas do
mês); a consistência do mês é uma conta nova e pequena, autocontida aqui."""

from __future__ import annotations

import calendar
from datetime import date

from app.application.history.weekly_buckets import activity_date, week_start
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)

_MONTH_NAMES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


class MonthlyRecapBuilder:

    @staticmethod
    def build(
        runner: RunnerProfile,
        history: TrainingHistory,
        month_start: date,
    ) -> dict | None:
        """`month_start` é o dia 1 do mês a recapitular (o mês que JÁ
        fechou). Retorna None se não houve nenhum treino nesse mês — nada a
        recapitular, sem mensagem vazia."""

        month_activities = [
            a for a in history.activities
            if MonthlyRecapBuilder._in_month(a, month_start)
        ]

        if not month_activities:

            return None

        total_km = sum(a.distance for a in month_activities) / 1000

        longest_km = max(a.distance for a in month_activities) / 1000

        return {
            "month_label": MonthlyRecapBuilder._month_label(month_start),
            "total_km": round(total_km, 1),
            "total_runs": len(month_activities),
            "longest_km": round(longest_km, 1),
            "consistency": MonthlyRecapBuilder._consistency(
                month_activities,
                runner.weekly_training_days,
                month_start,
            ),
            "records": MonthlyRecapBuilder._records_this_month(
                runner.id,
                month_start,
            ),
        }

    @staticmethod
    def _in_month(activity, month_start: date) -> bool:

        d = activity_date(activity)

        return d.year == month_start.year and d.month == month_start.month

    @staticmethod
    def _consistency(
        month_activities: list,
        weekly_training_days: int,
        month_start: date,
    ) -> float:

        if weekly_training_days <= 0:

            return 0.0

        days_trained = len(
            {activity_date(a) for a in month_activities}
        )

        days_in_month = calendar.monthrange(
            month_start.year,
            month_start.month,
        )[1]

        expected_days = round(weekly_training_days * days_in_month / 7)

        if expected_days <= 0:

            return 0.0

        return round(min(days_trained / expected_days, 1.0) * 100, 1)

    @staticmethod
    def _records_this_month(
        profile: str,
        month_start: date,
    ) -> list[str]:
        """Recordes cuja DATA cai dentro do mês — não os recordes de sempre,
        só o que de fato aconteceu neste mês específico."""

        records = PersonalRecordRepository().load(profile)

        if not records:

            return []

        lines: list[str] = []

        if MonthlyRecapBuilder._date_in_month(
            records.get("longest_km_date"), month_start,
        ):

            lines.append(
                f"🏆 Corrida mais longa: {records['longest_km']:.1f} km"
            )

        for band, band_date in (records.get("pace_by_band_dates") or {}).items():

            if MonthlyRecapBuilder._date_in_month(band_date, month_start):

                pace = records["pace_by_band"][band]

                lines.append(
                    f"⚡ Treino mais rápido na faixa {band} km: "
                    f"{MonthlyRecapBuilder._format_pace(pace)} min/km"
                )

        if MonthlyRecapBuilder._date_in_month(
            records.get("total_km_milestone_date"), month_start,
        ):

            lines.append(
                f"🎉 Passou de {records['total_km_milestone']} km "
                "acumulados com o RunMind"
            )

        best_week_key = records.get("best_week_key")

        if best_week_key and MonthlyRecapBuilder._week_in_month(
            best_week_key, month_start,
        ):

            lines.append(
                "📈 Semana de maior volume: "
                f"{records['best_week_km']:.1f} km"
            )

        return lines

    @staticmethod
    def _date_in_month(iso_date: str | None, month_start: date) -> bool:

        if not iso_date:

            return False

        d = date.fromisoformat(iso_date)

        return d.year == month_start.year and d.month == month_start.month

    @staticmethod
    def _week_in_month(week_key_str: str, month_start: date) -> bool:

        year_str, week_str = week_key_str.split("-W")

        start = week_start((int(year_str), int(week_str)))

        return start.year == month_start.year and start.month == month_start.month

    @staticmethod
    def _format_pace(pace_min_km: float) -> str:

        return PaceFormatter.format(pace_min_km)

    @staticmethod
    def _month_label(month_start: date) -> str:

        return f"{_MONTH_NAMES[month_start.month - 1]}/{month_start.year}"
