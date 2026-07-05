from app.application.planner.pace_formatter import PaceFormatter
from app.core.weekdays import WEEKDAYS
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_profile import RunnerProfile

# índice do dia da semana (segunda=0 ... domingo=6)
_DAY_INDEX = {name.lower(): i for i, name in WEEKDAYS.items()}

# Ritmos padrão quando o atleta não declara (caminhada de sedentário e
# trote bem leve). km/h -> min/km é 60 / kmh.
DEFAULT_WALK_KMH = 5.5   # ~10:54/km
DEFAULT_TROT_KMH = 7.5   # ~8:00/km

WARMUP_MIN = 5
COOLDOWN_MIN = 5
WALK_RECOVERY_SEC = 180        # caminhada de recuperação entre trotes
WALK_SESSION_MIN = 25          # duração da sessão de caminhada pura

# Iniciante de alto peso não faz run/walk todo dia: no máximo 3 dias,
# espaçados; os demais dias escolhidos viram caminhada.
MAX_RUN_WALK_DAYS = 3

# Progressão do trote ao longo das semanas (segundos e nº de repetições).
TROT_START_SEC = 30
TROT_STEP_SEC = 15
TROT_MAX_SEC = 90
REPS_START = 5
REPS_MAX = 8


class RunWalkEngine:
    """Trilha de corrida-caminhada para iniciante absoluto / alto IMC.

    Sessões medidas em TEMPO (não km): caminhada e blocos de trote curto
    intercalados com caminhada. Progride semana a semana e respeita a
    capacidade declarada no onboarding (quanto o atleta corre sem parar)."""

    @staticmethod
    def build(
        running_days: list[str],
        training_week: int,
        runner: RunnerProfile,
    ) -> list[PlannedSession]:

        days = sorted(
            running_days,
            key=lambda day: _DAY_INDEX.get(day.lower(), 0),
        )

        if not days:

            return []

        trot_sec, reps = RunWalkEngine._progression(training_week, runner)

        walk_pace = RunWalkEngine._walk_pace(runner)

        trot_pace = RunWalkEngine._trot_pace(runner)

        run_walk_days = RunWalkEngine._pick_run_walk_days(days)

        sessions = []

        for day in days:

            if day in run_walk_days:

                sessions.append(
                    RunWalkEngine._run_walk_session(
                        day, trot_sec, reps, walk_pace, trot_pace,
                    )
                )

            else:

                sessions.append(
                    RunWalkEngine._walk_session(day, walk_pace)
                )

        return sessions

    @staticmethod
    def _progression(
        training_week: int,
        runner: RunnerProfile,
    ) -> tuple[int, int]:

        week = max(training_week, 1)

        trot_sec = min(
            TROT_MAX_SEC,
            TROT_START_SEC + (week - 1) * TROT_STEP_SEC,
        )

        # nunca prescreve trote mais longo do que o atleta declara aguentar
        if runner.continuous_run_minutes:

            cap = int(runner.continuous_run_minutes * 60)

            trot_sec = min(trot_sec, max(TROT_START_SEC, cap))

        reps = min(REPS_MAX, REPS_START + (week - 1))

        return trot_sec, reps

    @staticmethod
    def _pick_run_walk_days(days: list[str]) -> set[str]:

        if len(days) <= MAX_RUN_WALK_DAYS:

            return set(days)

        # espaça os dias de run/walk (dia sim, dia não), limitado ao teto
        return set(days[::2][:MAX_RUN_WALK_DAYS])

    @staticmethod
    def _run_walk_session(
        day: str,
        trot_sec: int,
        reps: int,
        walk_pace: float,
        trot_pace: float,
    ) -> PlannedSession:

        active_sec = reps * (trot_sec + WALK_RECOVERY_SEC)

        total_min = WARMUP_MIN + COOLDOWN_MIN + round(active_sec / 60)

        return PlannedSession(
            day=day,
            workout_type="RUN_WALK",
            objective="Adaptação: alternar trote e caminhada",
            planned_distance_km=None,
            planned_duration_minutes=total_min,
            target_pace_min=PaceFormatter.format(trot_pace),
            target_pace_max=PaceFormatter.format(walk_pace),
            notes="",
            intervals={
                "warmup_min": WARMUP_MIN,
                "trot_sec": trot_sec,
                "walk_sec": WALK_RECOVERY_SEC,
                "reps": reps,
                "cooldown_min": COOLDOWN_MIN,
            },
        )

    @staticmethod
    def _walk_session(
        day: str,
        walk_pace: float,
    ) -> PlannedSession:

        return PlannedSession(
            day=day,
            workout_type="WALK",
            objective="Caminhada — base aeróbica e hábito",
            planned_distance_km=None,
            planned_duration_minutes=WALK_SESSION_MIN,
            target_pace_min=PaceFormatter.format(walk_pace),
            target_pace_max=PaceFormatter.format(walk_pace),
            notes="",
        )

    @staticmethod
    def _walk_pace(runner: RunnerProfile) -> float:

        return runner.walk_pace_min_km or (60 / DEFAULT_WALK_KMH)

    @staticmethod
    def _trot_pace(runner: RunnerProfile) -> float:

        return 60 / DEFAULT_TROT_KMH
