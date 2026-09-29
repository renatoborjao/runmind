"""'Carga da semana' da tela do Corpo — o que o atleta entende no lugar do ACWR
cru: quanto ele correu nesta semana (seg–dom) e qual é a média dele nas últimas
4 semanas completas. Os MESMOS dados das barras de volume da Evolução (semana de
calendário, só corrida, mesmas corridas de `merged_runs`), então a frase e o
gráfico nunca se contradizem.

É só fato, sem veredito: a semana em andamento ainda está sendo escrita, e quem
julga carga × recuperação é o coach (radar em [[TrainingLoadAnalyzer]])."""

from __future__ import annotations

from datetime import date
from statistics import mean

from app.application.history.run_merge import merged_runs
from app.application.history.weekly_buckets import (
    group_by_week,
    last_week_keys,
    week_start,
)
from app.core.clock import now_local
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

# semanas COMPLETAS que formam a média dele
_AVG_WEEKS = 4


class WeekLoadBuilder:

    @staticmethod
    def build(profile: str, today: date | None = None) -> dict | None:
        """None sem nenhuma corrida no histórico (a tela esconde o card)."""

        runs = merged_runs(profile)

        if not runs:

            return None

        today = today or now_local().date()

        buckets = group_by_week(runs)

        *past, current = last_week_keys(today, _AVG_WEEKS + 1)

        def km(key) -> float:

            return sum(a.distance for a in buckets.get(key, [])) / 1000

        # semana parada (férias, doença) não vira "a média dele"
        active = [k for k in past if buckets.get(k)]

        avg_km = avg_runs = None

        if len(active) >= 2:

            avg_km = round(mean(km(k) for k in active), 1)

            avg_runs = round(mean(len(buckets[k]) for k in active), 1)

        monday = week_start(current)

        return {
            "km": round(km(current), 1),
            "runs": len(buckets.get(current, [])),
            "planned_runs": WeekLoadBuilder._planned_runs(profile, monday),
            "avg_km": avg_km,
            "avg_runs": avg_runs,
        }

    @staticmethod
    def _planned_runs(profile: str, monday: date) -> int | None:
        """Treinos do PLANO desta semana de calendário. O plano da semana que vem
        nasce no domingo, então só conta quando o plano carregado é o desta
        semana — senão None (não chuta)."""

        try:

            plan = WeeklyPlanRepository().load(profile)

        except Exception as e:  # noqa: BLE001

            print(f"Plano indisponível p/ carga da semana de '{profile}': {e}")

            return None

        if plan is None:

            return None

        start = getattr(plan, "week_start", None)

        if isinstance(start, str):

            try:

                start = date.fromisoformat(start[:10])

            except ValueError:

                return None

        if start != monday:

            return None

        return len(plan.sessions) or None
