"""Evolução SEMANA A SEMANA do atleta — a base pro coach decidir pela
TRAJETÓRIA, não só pelo retrato de hoje: como o volume subiu/caiu, se o longão
cresceu, como a ECONOMIA aeróbica andou e como o corpo/sono estava em cada
semana. Com isso o coach responde "dá pra 8 km amanhã?" olhando como o atleta
absorveu semanas parecidas.

A economia é a MESMA medida da leitura "Forma"/"estou evoluindo?" (o
[[AerobicEfficiencyAnalyzer]]: velocidade ÷ FC nas corridas aeróbicas
comparáveis, ajustada por calor e relevo, sem provas) — aqui só aberta semana a
semana. Antes esta tabela usava "batimentos por km" bruto de todas as corridas
(confundido por intensidade e calor) e dizia "menos eficiente" enquanto a
Forma dizia "8 s/km mais rápido na mesma FC": o coach podia defender as duas.
Uma verdade só. Puro/determinístico. Ver [[feedback_base_historico_sempre]]."""

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.application.history.aerobic_efficiency_analyzer import (
    AerobicEfficiencyAnalyzer,
)
from app.core.clock import active_timezone, today_local
from app.domain.entities.activity import Activity
from app.domain.entities.body_reading_snapshot import BodyReadingSnapshot
from app.domain.value_objects.sports import is_run_sport

DEFAULT_WEEKS = 8

# fragmento/registro solto não é treino (alinha com o resto do sistema)
_MIN_DISTANCE_M = 1000

_BODY_PT = {
    "STRAINED": "sobrecarregado",
    "RECOVERY_FLAG": "recuperação em queda",
    "ABSORBING": "absorvendo bem",
    "BALANCED": "equilibrado",
    "FRESH": "descansado",
    "BUILDING": "montando base",
}


@dataclass(slots=True)
class WeekStat:

    start: date
    runs: int
    km: float
    longest_km: float
    pace_sec: int | None          # pace médio bruto (tempo total / km total)
    avg_hr: int | None            # FC média ponderada pelo tempo
    aerobic_pace_sec: int | None  # economia: pace na FC de referência (ajustado)
    body: BodyReadingSnapshot | None  # última leitura do corpo da semana


class WeeklyEvolutionDigest:

    @staticmethod
    def for_profile(profile: str) -> str:
        """Render do atleta com a MESMA matéria-prima da leitura "Forma"
        (arquivo, FC de repouso/máx, sem provas) + leituras do corpo.
        Best-effort: falha vira "" (nunca derruba quem chama)."""

        try:

            from app.application.coach.intelligence.fitness_reading_service import (
                FitnessReadingService,
            )
            from app.application.coach.writer.fitness_evolution_writer import (
                FitnessEvolutionWriter,
            )
            from app.infrastructure.persistence.body_reading_history_repository import (
                BodyReadingHistoryRepository,
            )

            activities, _series, resting_hr, max_hr = FitnessReadingService._load(
                profile
            )

            evolution = FitnessEvolutionWriter.line(
                FitnessReadingService.read_evolution(profile)
            )

            return WeeklyEvolutionDigest.render(
                activities,
                BodyReadingHistoryRepository().load(profile),
                today_local(),
                resting_hr=resting_hr,
                max_hr=max_hr,
                ef_activities=FitnessReadingService._without_races(
                    profile, activities
                ),
                evolution_line=evolution or "",
            )

        except Exception as e:

            print(f"Evolução semanal falhou p/ '{profile}': {e}")

            return ""

    @staticmethod
    def build(
        activities: list[Activity],
        snapshots: list[BodyReadingSnapshot],
        today: date,
        weeks: int = DEFAULT_WEEKS,
        resting_hr: int | None = None,
        max_hr: int | None = None,
        ef_activities: list[Activity] | None = None,
    ) -> tuple[list[WeekStat], int | None]:
        """(uma linha por semana seg–dom, da mais ANTIGA pra atual — incluindo
        semanas sem corrida —, FC de referência da economia)."""

        current = today - timedelta(days=today.weekday())

        starts = [current - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]

        buckets: dict[date, list[Activity]] = {s: [] for s in starts}

        for act in activities:

            if not is_run_sport(act.sport) or (act.distance or 0) < _MIN_DISTANCE_M:

                continue

            week = WeeklyEvolutionDigest._week_of(act.start_date)

            if week in buckets:

                buckets[week].append(act)

        body_by_week: dict[date, BodyReadingSnapshot] = {}

        for snap in snapshots:  # antigo -> novo: a última da semana prevalece

            week = snap.day - timedelta(days=snap.day.weekday())

            if week in buckets:

                body_by_week[week] = snap

        # economia: as MESMAS corridas comparáveis da leitura "Forma"
        comparable = AerobicEfficiencyAnalyzer._comparable_runs(
            ef_activities if ef_activities is not None else activities,
            starts[0],
            today,
            resting_hr,
            max_hr,
        )

        ref_hr = (
            round(statistics.median(r["hr"] for r in comparable))
            if comparable else None
        )

        ef_by_week: dict[date, list[float]] = {}

        for run in comparable:

            week = run["day"] - timedelta(days=run["day"].weekday())

            ef_by_week.setdefault(week, []).append(run["ef"])

        stats = [
            WeeklyEvolutionDigest._week_stat(
                s, buckets[s], body_by_week.get(s), ef_by_week.get(s), ref_hr,
            )
            for s in starts
        ]

        return stats, ref_hr

    @staticmethod
    def render(
        activities: list[Activity],
        snapshots: list[BodyReadingSnapshot],
        today: date,
        weeks: int = DEFAULT_WEEKS,
        resting_hr: int | None = None,
        max_hr: int | None = None,
        ef_activities: list[Activity] | None = None,
        evolution_line: str = "",
    ) -> str:
        """Tabela compacta + tendência. Vazio sem corrida no período."""

        stats, ref_hr = WeeklyEvolutionDigest.build(
            activities, snapshots, today, weeks, resting_hr, max_hr,
            ef_activities,
        )

        if not any(s.runs for s in stats):

            return ""

        economy = (
            f"economia = pace nas corridas aeróbicas levado à FC de referência "
            f"~{ref_hr} bpm, ajustado por calor/relevo (MENOR = mais em forma) — "
            "é a mesma medida da leitura 'Forma'"
            if ref_hr else "sem corridas aeróbicas comparáveis pra medir economia"
        )

        lines = [
            f"EVOLUÇÃO SEMANA A SEMANA (últimas {weeks}, seg–dom; {economy}; "
            "decida pela TRAJETÓRIA e por como ele absorveu semanas parecidas, "
            "não só pelo dia):"
        ]

        current = today - timedelta(days=today.weekday())

        for s in stats:

            label = f"{s.start:%d/%m}"

            if s.start == current:

                label += " (em andamento)"

            if not s.runs:

                line = f"- {label}: sem corrida"

            else:

                parts = [
                    f"{s.runs}x",
                    f"{s.km:.1f} km",
                    f"maior {s.longest_km:.1f} km",
                ]

                if s.pace_sec:

                    parts.append(f"pace {WeeklyEvolutionDigest._pace(s.pace_sec)}")

                if s.avg_hr:

                    parts.append(f"FC {s.avg_hr}")

                if s.aerobic_pace_sec:

                    parts.append(
                        f"economia {WeeklyEvolutionDigest._pace(s.aerobic_pace_sec)}"
                    )

                line = f"- {label}: " + ", ".join(parts)

            body = WeeklyEvolutionDigest._body_text(s.body)

            if body:

                line += f" | corpo: {body}"

            lines.append(line)

        trend = WeeklyEvolutionDigest._volume_trend(stats, current)

        if evolution_line:

            trend = (
                f"{trend} " if trend else ""
            ) + f"Forma (a leitura oficial, 8 semanas): {evolution_line}"

        if trend:

            lines.append(trend)

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @staticmethod
    def _week_of(moment: datetime) -> date:

        day = (
            moment.date()
            if moment.tzinfo is None
            else moment.astimezone(active_timezone()).date()
        )

        return day - timedelta(days=day.weekday())

    @staticmethod
    def _week_stat(
        start: date,
        acts: list[Activity],
        body: BodyReadingSnapshot | None,
        efs: list[float] | None,
        ref_hr: int | None,
    ) -> WeekStat:

        total_m = sum(a.distance or 0 for a in acts)

        total_s = sum(a.moving_time or 0 for a in acts)

        with_hr = [a for a in acts if a.average_heartrate and a.moving_time]

        hr_time = sum(a.moving_time for a in with_hr)

        aerobic_pace = None

        if efs and ref_hr:

            # EF (m/s por batimento) × FC de referência = velocidade → pace
            speed = statistics.median(efs) * ref_hr

            aerobic_pace = round(1000 / speed) if speed > 0 else None

        return WeekStat(
            start=start,
            runs=len(acts),
            km=round(total_m / 1000, 1),
            longest_km=round(max((a.distance or 0 for a in acts), default=0) / 1000, 1),
            pace_sec=(
                round(total_s / (total_m / 1000))
                if total_m > 0 and total_s > 0 else None
            ),
            avg_hr=(
                round(sum(a.average_heartrate * a.moving_time for a in with_hr) / hr_time)
                if hr_time else None
            ),
            aerobic_pace_sec=aerobic_pace,
            body=body,
        )

    @staticmethod
    def _body_text(body: BodyReadingSnapshot | None) -> str:

        if body is None:

            return ""

        parts = [_BODY_PT.get(body.body_state, body.body_state.lower())]

        if body.sleep_avg_hours:

            parts.append(f"sono {body.sleep_avg_hours:.1f}h")

        if body.hrv_recent:

            parts.append(f"HRV {body.hrv_recent:.0f}")

        if body.rhr_recent:

            parts.append(f"FC repouso {body.rhr_recent}")

        return ", ".join(parts)

    @staticmethod
    def _volume_trend(stats: list[WeekStat], current: date) -> str:
        """Volume: últimas 4 semanas FECHADAS × as 4 anteriores (a semana em
        andamento fica fora — parcial distorce). A economia NÃO entra aqui:
        a tendência oficial dela é a da leitura 'Forma' (regressão)."""

        closed = [s for s in stats if s.start != current]

        recent, before = closed[-4:], closed[-8:-4]

        if len(recent) < 2 or len(before) < 2:

            return ""

        def avg_km(group):

            return sum(s.km for s in group) / len(group)

        return (
            f"Tendência de volume (média das 4 semanas fechadas × as 4 "
            f"anteriores, semana sem corrida conta zero): "
            f"{avg_km(before):.0f} → {avg_km(recent):.0f} km/sem."
        )

    @staticmethod
    def _pace(sec_per_km: int) -> str:

        minutes, seconds = divmod(int(sec_per_km), 60)

        return f"{minutes}:{seconds:02d}"
