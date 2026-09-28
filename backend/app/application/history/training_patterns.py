"""PADRÕES RECENTES do atleta — o que SE REPETE nas últimas semanas, com o
dado na mão. É a base pro coach elogiar com fundamento E puxar a orelha com
fundamento (nunca por um dia isolado). Varredura de 26/09: o coach elogiava a
"parte leve" do longão em Z3/Z4, via "resiliência" em 10 dias de recuperação
em queda e nunca notava que o atleta vinha estourando o combinado — porque
nada disso chegava até ele como PADRÃO.

Cruza: plano (o que foi pedido) × corrida real do mesmo dia (arquivo
deduplicado, com zonas de FC do relógio) × RPE que o atleta respondeu × leituras
do corpo (sono, FC de repouso, HRV). Puro/determinístico. Ver
[[project_cardapio_treinos]] e [[feedback_base_historico_sempre]]."""

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.application.history.stimulus_ledger import (
    EASY,
    LONG,
    StimulusLedger,
)
from app.core.clock import active_timezone, today_local
from app.domain.entities.activity import Activity
from app.domain.entities.body_reading_snapshot import BodyReadingSnapshot
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.value_objects.sports import is_run_sport

WINDOW_WEEKS = 4

_MIN_DISTANCE_M = 1000

# teto AERÓBICO pela reserva de FC (Karvonen 70%) — mesma fisiologia pra todo
# atleta, independente de como o relógio dele está configurado. As zonas por
# %FCmáx do Garmin puxam o Z3 pra baixo (Fernanda: Z3 = 129 bpm) e acusariam
# "leve forte" em qualquer trote; a reserva usa a FC de repouso real dele.
_AEROBIC_HRR = 0.70

# longão-base pode derivar um pouco no fim (calor/duração) sem ser "forte"
_LONG_DRIFT_BPM = 3

# passou do combinado num dia leve / cortou a sessão-chave
_OVERSHOOT = 1.15
_CUT_SHORT = 0.85

# longão com qualidade dentro (progressivo/misto/blocos) pode ter Z3+ — fora
_LONG_QUALITY_CUES = ("progress", "misto", "bloco", "final", "ritmo", "prova")

# piora OBJETIVA da recuperação vs a base do próprio atleta
_RHR_WORSE_BPM = 4
_HRV_WORSE_RATIO = 0.10
_BASELINE_MIN_DAYS = 21
_BASELINE_MAX_DAYS = 70

_ALERT_STATES = {"RECOVERY_FLAG", "STRAINED"}


@dataclass(slots=True)
class RecoveryDrift:
    """Recuperação AGORA × a base do atleta (semanas atrás)."""

    rhr_now: float | None
    rhr_base: float | None
    hrv_now: float | None
    hrv_base: float | None
    alert_streak: int
    sleep_avg: float | None
    short_nights: int
    nights: int

    @property
    def worsening(self) -> bool:
        """Piora de VERDADE (não o baseline dele): em alerta há 3+ leituras E
        FC de repouso subiu / HRV caiu de forma material vs a própria base."""

        if self.alert_streak < 3:

            return False

        rhr_up = (
            self.rhr_now is not None and self.rhr_base is not None
            and self.rhr_now - self.rhr_base >= _RHR_WORSE_BPM
        )

        hrv_down = (
            self.hrv_now is not None and self.hrv_base
            and (self.hrv_base - self.hrv_now) / self.hrv_base >= _HRV_WORSE_RATIO
        )

        return bool(rhr_up or hrv_down)


class TrainingPatterns:

    @staticmethod
    def recovery_drift(snapshots: list[BodyReadingSnapshot]) -> RecoveryDrift | None:

        if not snapshots:

            return None

        latest = snapshots[-1]

        streak = 0

        for snap in reversed(snapshots):

            if snap.body_state not in _ALERT_STATES:

                break

            streak += 1

        recent = snapshots[-3:]

        base = [
            s for s in snapshots
            if _BASELINE_MIN_DAYS <= (latest.day - s.day).days <= _BASELINE_MAX_DAYS
        ]

        def med(items, attr):

            values = [getattr(s, attr) for s in items if getattr(s, attr)]

            return statistics.median(values) if values else None

        return RecoveryDrift(
            rhr_now=med(recent, "rhr_recent"),
            rhr_base=med(base, "rhr_recent") if len(base) >= 2 else None,
            hrv_now=med(recent, "hrv_recent"),
            hrv_base=med(base, "hrv_recent") if len(base) >= 2 else None,
            alert_streak=streak,
            sleep_avg=latest.sleep_avg_hours,
            short_nights=latest.short_nights,
            nights=latest.nights_counted,
        )

    @staticmethod
    def render(
        plans: list[TrainingPlan],
        activities: list[Activity],
        snapshots: list[BodyReadingSnapshot],
        rpes: list,
        today: date,
        weeks: int = WINDOW_WEEKS,
        ceiling: int | None = None,
        drift: RecoveryDrift | None = None,
    ) -> str:
        """`drift` pronta (com a leitura de HOJE) vence a dos snapshots — é a
        mesma que o estado do corpo usa, pra não sair número diferente."""

        lines: list[str] = []

        sessions = TrainingPatterns._sessions(plans, activities, today, weeks)

        past = [s for s in sessions if s[0] < today or s[3] is not None]

        if past:

            done = sum(1 for s in past if s[3] is not None)

            missed = [s for s in past if s[3] is None and s[0] < today]

            text = f"- Aderência: fez {done} de {len(past)} sessões do plano"

            if missed:

                fams = ", ".join(sorted({s[2] for s in missed}))

                text += f" (furou {len(missed)}: {fams})"

            lines.append(text + ".")

            lines += TrainingPatterns._intent_lines(past, ceiling)

        lines += TrainingPatterns._volume_lines(plans, activities, today, weeks)

        lines += TrainingPatterns._rpe_lines(sessions, rpes)

        drift = drift or TrainingPatterns.recovery_drift(snapshots)

        if drift is not None:

            lines += TrainingPatterns._body_lines(drift)

        if not lines:

            return ""

        return (
            f"PADRÕES RECENTES (últimas {weeks} semanas — o que SE REPETE, com "
            "o dado; é a base pra elogiar ou cobrar com fundamento, nunca por "
            "um dia isolado):\n" + "\n".join(lines)
        )

    @staticmethod
    def for_profile(profile: str, drift: RecoveryDrift | None = None) -> str:
        """Render a partir do storage. Best-effort: falha vira ""."""

        try:

            from app.infrastructure.persistence.activity_archive_repository import (
                ActivityArchiveRepository,
            )
            from app.infrastructure.persistence.body_reading_history_repository import (
                BodyReadingHistoryRepository,
            )
            from app.infrastructure.persistence.session_rpe_repository import (
                SessionRpeRepository,
            )
            from app.infrastructure.persistence.weekly_plan_repository import (
                WeeklyPlanRepository,
            )

            repo = WeeklyPlanRepository()

            plans = list(repo.history(profile))

            current = repo.load(profile)

            if current is not None:

                plans.append(current)

            activities = ActivityArchiveRepository().load_activities(profile)

            return TrainingPatterns.render(
                plans,
                activities,
                BodyReadingHistoryRepository().load(profile),
                SessionRpeRepository().load_sessions(profile),
                today_local(),
                ceiling=TrainingPatterns._ceiling_for(profile, activities),
                drift=drift,
            )

        except Exception as e:

            print(f"Padrões recentes falharam p/ '{profile}': {e}")

            return ""

    @staticmethod
    def _ceiling_for(profile: str, activities: list) -> int | None:
        """Teto aeróbico do atleta pela régua única de FC (máx do relógio/pico
        real + repouso atual). Sem repouso, None — melhor não cobrar do que
        cobrar com régua errada."""

        try:

            from app.application.history.hr_zone_resolver import HrZoneResolver
            from app.application.use_cases.load_runner_profile import (
                LoadRunnerProfile,
            )

            zones = HrZoneResolver.for_profile(
                profile, LoadRunnerProfile.execute(profile), activities,
            )

            if zones is None:

                return None

            return TrainingPatterns.aerobic_ceiling(zones.max_hr, zones.resting_hr)

        except Exception as e:

            print(f"Teto aeróbico falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    def drift_for_profile(profile: str) -> RecoveryDrift | None:

        try:

            from app.infrastructure.persistence.body_reading_history_repository import (
                BodyReadingHistoryRepository,
            )

            return TrainingPatterns.recovery_drift(
                BodyReadingHistoryRepository().load(profile)
            )

        except Exception as e:

            print(f"Drift de recuperação falhou p/ '{profile}': {e}")

            return None

    # ------------------------------------------------------------------

    @staticmethod
    def _sessions(
        plans: list[TrainingPlan],
        activities: list[Activity],
        today: date,
        weeks: int,
    ) -> list[tuple[date, PlannedSession, str, Activity | None]]:
        """(dia, sessão, família, corrida que a cumpriu ou None) na janela,
        ordenado. O casamento é o do app inteiro ([[WeeklyPlanMatcher]]: dia,
        depois distância, longão maior conta) — casar só pelo dia contava
        "furou o longão" de quem só trocou o dia (Fernanda)."""

        from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher

        start = today - timedelta(weeks=weeks)

        runs = [
            a for a in activities
            if is_run_sport(a.sport) and (a.distance or 0) >= _MIN_DISTANCE_M
        ]

        weeks_plans = {p.week_start: p for p in plans}

        out = []

        for plan in weeks_plans.values():

            for session, act in WeeklyPlanMatcher.pairs(plan, runs):

                if getattr(session, "kind", "run") not in ("run", "walk", "run_walk"):

                    continue

                day = plan.session_date(session)

                # fora da janela; e sessão futura só entra se JÁ foi cumprida
                # (ex.: o longão de domingo feito no sábado)
                if day < start or (day > today and act is None):

                    continue

                out.append((
                    day,
                    session,
                    StimulusLedger.classify(session.workout_type),
                    act,
                ))

        return sorted(out, key=lambda s: s[0])

    @staticmethod
    def aerobic_ceiling(max_hr: int | None, resting_hr: int | None) -> int | None:
        """Teto aeróbico (FC) pela reserva: repouso + 70% × (máx − repouso)."""

        if not max_hr or not resting_hr or max_hr <= resting_hr:

            return None

        return round(resting_hr + _AEROBIC_HRR * (max_hr - resting_hr))

    @staticmethod
    def _intent_lines(sessions, ceiling: int | None = None) -> list[str]:
        """Intenção × execução: leve/longão-base saindo forte (FC média acima
        do teto aeróbico dele), estourar o combinado no dia leve, cortar a
        sessão-chave."""

        lines = []

        easy_checked, easy_hard, easy_hrs = 0, [], []

        overshoot, cut = [], []

        for day, session, family, act in sessions:

            if act is None:

                continue

            norm = StimulusLedger._normalize(session.workout_type)

            is_long = family == LONG

            aerobic = family == EASY or (
                is_long and not any(c in norm for c in _LONG_QUALITY_CUES)
            )

            hr = act.average_heartrate

            if aerobic and ceiling and hr:

                easy_checked += 1

                easy_hrs.append(hr)

                limit = ceiling + (_LONG_DRIFT_BPM if is_long else 0)

                if hr >= limit:

                    easy_hard.append(f"{day:%d/%m} ({hr:.0f} bpm)")

            ratio = TrainingPatterns._volume_ratio(session, act)

            if ratio is None:

                continue

            if family == EASY and ratio >= _OVERSHOOT:

                overshoot.append(f"{day:%d/%m} (+{(ratio - 1) * 100:.0f}%)")

            if family != EASY and ratio <= _CUT_SHORT:

                cut.append(f"{day:%d/%m} {session.workout_type} ({ratio * 100:.0f}%)")

        if easy_checked:

            avg = sum(easy_hrs) / len(easy_hrs)

            if easy_hard:

                lines.append(
                    f"- Leve/longão-base saindo FORTE: {len(easy_hard)} de "
                    f"{easy_checked} com FC média acima do teto aeróbico dele "
                    f"(~{ceiling} bpm, 70% da reserva de FC): "
                    f"{', '.join(easy_hard)}; média dos leves {avg:.0f} bpm."
                )

            else:

                lines.append(
                    f"- Leve/longão-base no controle: {easy_checked} treinos "
                    f"abaixo do teto aeróbico (~{ceiling} bpm), média {avg:.0f} "
                    "bpm — leve de verdade."
                )

        if overshoot:

            lines.append(
                "- Passou do combinado em dia LEVE: " + ", ".join(overshoot)
                + " (no leve, o combinado é teto — sobra vira carga)."
            )

        if cut:

            lines.append(
                "- Encurtou sessão importante: " + ", ".join(cut) + "."
            )

        return lines

    @staticmethod
    def _volume_lines(plans, activities, today: date, weeks: int) -> list[str]:
        """Semana FECHADA com o executado longe do plano (±20%): treino extra
        e estouro viram carga não planejada (maurício: 28 → 43 km) — e semana
        muito abaixo é sinal de rotina/fadiga. Só semanas fechadas."""

        current = today - timedelta(days=today.weekday())

        start = current - timedelta(weeks=weeks)

        by_week = {p.week_start: p for p in plans}

        run_km: dict[date, float] = {}

        for act in activities:

            if not is_run_sport(act.sport) or (act.distance or 0) < _MIN_DISTANCE_M:

                continue

            day = TrainingPatterns._local_day(act.start_date)

            week = day - timedelta(days=day.weekday())

            run_km[week] = run_km.get(week, 0.0) + act.distance / 1000

        deviations = []

        for week in sorted(by_week):

            if not (start <= week < current):

                continue

            plan = by_week[week]

            planned = plan.weekly_volume or sum(
                s.planned_distance_km or 0 for s in plan.sessions
            )

            if not planned or planned <= 0:

                continue

            done = run_km.get(week, 0.0)

            ratio = done / planned

            if abs(ratio - 1) >= 0.20:

                deviations.append(
                    f"{week:%d/%m} plano ~{planned:.0f} → fez {done:.0f} km "
                    f"({(ratio - 1) * 100:+.0f}%)"
                )

        if not deviations:

            return []

        return [
            "- Volume da semana × plano: " + ", ".join(deviations)
            + " (acima = carga NÃO planejada que o corpo paga; abaixo = rotina "
            "ou cansaço travando)."
        ]

    @staticmethod
    def _volume_ratio(session: PlannedSession, act: Activity) -> float | None:
        """Executado / planejado (distância, ou tempo no treino por tempo)."""

        if session.planned_distance_km:

            return (act.distance / 1000) / session.planned_distance_km

        if session.planned_duration_minutes and act.moving_time:

            return (act.moving_time / 60) / session.planned_duration_minutes

        return None

    @staticmethod
    def _rpe_lines(sessions, rpes) -> list[str]:
        """Percepção × intenção: leve sentido pesado é sinal (fadiga)."""

        by_day = {str(getattr(r, "day", "")): r for r in rpes or []}

        heavy_easy = []

        for day, session, family, act in sessions:

            rpe = by_day.get(day.isoformat())

            if rpe is None or getattr(rpe, "rpe", None) is None:

                continue

            if family == EASY and rpe.rpe >= 6:

                heavy_easy.append(f"{day:%d/%m} ({rpe.rpe}/10)")

        lines = []

        if heavy_easy:

            lines.append(
                "- Leve SENTIDO pesado: " + ", ".join(heavy_easy)
                + " (percepção alta no leve = fadiga acumulando)."
            )

        return lines

    @staticmethod
    def _body_lines(drift: RecoveryDrift) -> list[str]:

        lines = []

        if drift.sleep_avg:

            short = (
                f", {drift.short_nights} de {drift.nights} noites curtas"
                if drift.nights else ""
            )

            lines.append(f"- Sono: média {drift.sleep_avg:.1f}h{short}.")

        if drift.alert_streak:

            lines.append(
                f"- Corpo em alerta há {drift.alert_streak} leituras seguidas."
            )

        trend = []

        if drift.rhr_now and drift.rhr_base:

            trend.append(
                f"FC de repouso {drift.rhr_base:.0f} → {drift.rhr_now:.0f} bpm"
            )

        if drift.hrv_now and drift.hrv_base:

            trend.append(f"HRV {drift.hrv_base:.0f} → {drift.hrv_now:.0f}")

        if trend:

            verdict = (
                "PIORA REAL da recuperação (não é o normal dele)"
                if drift.worsening
                else "dentro da faixa dele"
            )

            lines.append(
                "- Recuperação vs a base de semanas atrás: "
                + ", ".join(trend) + f" — {verdict}."
            )

        return lines

    @staticmethod
    def _local_day(moment: datetime) -> date:

        if moment.tzinfo is None:

            return moment.date()

        return moment.astimezone(active_timezone()).date()
