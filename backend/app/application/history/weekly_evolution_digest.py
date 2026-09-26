"""Evolução SEMANA A SEMANA do atleta — a base pro coach decidir pela
TRAJETÓRIA, não só pelo retrato de hoje. O retrato (build_portrait) dá médias
e o máximo; o corpo dá o agora. Faltava a curva: como o volume subiu/caiu, se
o longão cresceu, se o custo cardíaco (batimentos por km) está caindo — que é
evolução aeróbica de verdade — e como o corpo/sono andou em cada semana. Com
isso o coach responde "dá pra 8 km amanhã?" olhando como ele absorveu semanas
parecidas. Puro/determinístico. Ver [[feedback_base_historico_sempre]]."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

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
    pace_sec: int | None        # pace médio (tempo total / km total)
    avg_hr: int | None          # FC média ponderada pelo tempo
    beats_per_km: int | None    # custo cardíaco: menor = mais eficiente
    body: BodyReadingSnapshot | None  # última leitura do corpo da semana


class WeeklyEvolutionDigest:

    @staticmethod
    def for_profile(profile: str) -> str:
        """Render do atleta a partir do arquivo (deduplicado) + leituras do
        corpo. Best-effort: falha vira "" (nunca derruba quem chama)."""

        try:

            from app.infrastructure.persistence.activity_archive_repository import (
                ActivityArchiveRepository,
            )
            from app.infrastructure.persistence.body_reading_history_repository import (
                BodyReadingHistoryRepository,
            )

            return WeeklyEvolutionDigest.render(
                ActivityArchiveRepository().load_activities(profile),
                BodyReadingHistoryRepository().load(profile),
                today_local(),
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
    ) -> list[WeekStat]:
        """Uma linha por semana (seg–dom), da mais ANTIGA pra atual, incluindo
        semanas sem corrida (buraco também é informação)."""

        current = today - timedelta(days=today.weekday())

        starts = [current - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]

        buckets: dict[date, list[Activity]] = {s: [] for s in starts}

        for act in activities:

            if not is_run_sport(act.sport) or (act.distance or 0) < _MIN_DISTANCE_M:

                continue

            day = WeeklyEvolutionDigest._local_day(act.start_date)

            week = day - timedelta(days=day.weekday())

            if week in buckets:

                buckets[week].append(act)

        body_by_week: dict[date, BodyReadingSnapshot] = {}

        for snap in snapshots:  # antigo -> novo: a última da semana prevalece

            week = snap.day - timedelta(days=snap.day.weekday())

            if week in buckets:

                body_by_week[week] = snap

        return [
            WeeklyEvolutionDigest._week_stat(s, buckets[s], body_by_week.get(s))
            for s in starts
        ]

    @staticmethod
    def render(
        activities: list[Activity],
        snapshots: list[BodyReadingSnapshot],
        today: date,
        weeks: int = DEFAULT_WEEKS,
    ) -> str:
        """Tabela compacta + leitura da tendência. Vazio sem corrida no
        período (nada é inventado)."""

        stats = WeeklyEvolutionDigest.build(activities, snapshots, today, weeks)

        if not any(s.runs for s in stats):

            return ""

        lines = [
            f"EVOLUÇÃO SEMANA A SEMANA (últimas {weeks}, seg–dom; bpm/km = "
            "custo cardíaco, MENOR = mais eficiente — sobe em semana com mais "
            "treino forte/calor; decida pela TRAJETÓRIA e por como ele "
            "absorveu semanas parecidas, não só pelo dia):"
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

                if s.beats_per_km:

                    parts.append(f"{s.beats_per_km} bpm/km")

                line = f"- {label}: " + ", ".join(parts)

            body = WeeklyEvolutionDigest._body_text(s.body)

            if body:

                line += f" | corpo: {body}"

            lines.append(line)

        trend = WeeklyEvolutionDigest._trend(stats, current)

        if trend:

            lines.append(trend)

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @staticmethod
    def _local_day(moment: datetime) -> date:

        if moment.tzinfo is None:

            return moment.date()

        return moment.astimezone(active_timezone()).date()

    @staticmethod
    def _week_stat(
        start: date,
        acts: list[Activity],
        body: BodyReadingSnapshot | None,
    ) -> WeekStat:

        total_m = sum(a.distance or 0 for a in acts)

        total_s = sum(a.moving_time or 0 for a in acts)

        with_hr = [
            a for a in acts
            if a.average_heartrate and a.moving_time and a.distance
        ]

        hr_time = sum(a.moving_time for a in with_hr)

        hr_km = sum(a.distance for a in with_hr) / 1000

        beats = sum(a.average_heartrate * a.moving_time / 60 for a in with_hr)

        return WeekStat(
            start=start,
            runs=len(acts),
            km=round(total_m / 1000, 1),
            longest_km=round(max((a.distance or 0 for a in acts), default=0) / 1000, 1),
            pace_sec=(
                round(total_s / (total_m / 1000))
                if total_m > 0 and total_s > 0 else None
            ),
            avg_hr=round(beats / (hr_time / 60)) if hr_time else None,
            beats_per_km=round(beats / hr_km) if hr_km > 0 else None,
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
    def _trend(stats: list[WeekStat], current: date) -> str:
        """Últimas 4 semanas FECHADAS × as 4 anteriores: volume e custo
        cardíaco. A semana em andamento fica fora (parcial distorce)."""

        closed = [s for s in stats if s.start != current]

        recent, before = closed[-4:], closed[-8:-4]

        if len(recent) < 2 or len(before) < 2:

            return ""

        def avg_km(group):

            return sum(s.km for s in group) / len(group)

        def avg_bpk(group):

            values = [s.beats_per_km for s in group if s.beats_per_km]

            return sum(values) / len(values) if values else None

        text = (
            f"Tendência (4 semanas fechadas × 4 anteriores): volume "
            f"{avg_km(before):.0f} → {avg_km(recent):.0f} km/sem"
        )

        b_before, b_recent = avg_bpk(before), avg_bpk(recent)

        if b_before and b_recent:

            text += (
                f"; custo cardíaco {b_before:.0f} → {b_recent:.0f} bpm/km "
                f"({'mais eficiente' if b_recent < b_before else 'menos eficiente'})"
            )

        return text + "."

    @staticmethod
    def _pace(sec_per_km: int) -> str:

        minutes, seconds = divmod(int(sec_per_km), 60)

        return f"{minutes}:{seconds:02d}"
