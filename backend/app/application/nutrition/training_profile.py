"""O TREINO do atleta como a nutrição precisa enxergar: quantas vezes treina,
o que o plano manda cada dia (tipo, distância, duração, gasto) e o que ele FAZ
de verdade (volume/frequência reais). Fato, não opinião — entra no prompt do
cardápio pra IA dimensionar e ENCAIXAR a comida no treino (pré/pós, dia de
longão, véspera)."""

from __future__ import annotations

from app.application.home.home_summary_builder import _kind, planned_km
from app.application.nutrition import nutrition_targets as nt

# pace de fallback (min/km) quando a sessão não traz alvo
DEFAULT_PACE_MIN_KM = 6.25


def _pace(value) -> float | None:
    """'6:20' → 6.33 (min/km); None se não der pra ler."""

    try:

        m, s = str(value).strip().split(":")[:2]

        return int(m) + int(s) / 60

    except (ValueError, TypeError, AttributeError):

        return None


def session_load(session) -> tuple[float | None, int | None]:
    """(km, minutos) estimados da sessão planejada. Completa um com o outro
    pelo pace-alvo (ou o padrão)."""

    if session is None:

        return None, None

    km = planned_km(session) or getattr(session, "estimated_distance_km", None)

    minutes = getattr(session, "planned_duration_minutes", None)

    paces = [
        p for p in (
            _pace(getattr(session, "target_pace_min", None)),
            _pace(getattr(session, "target_pace_max", None)),
        ) if p
    ]

    pace = sum(paces) / len(paces) if paces else DEFAULT_PACE_MIN_KM

    if km and not minutes:

        minutes = round(km * pace)

    elif minutes and not km:

        km = round(minutes / pace, 1)

    return (round(km, 1) if km else None), (int(minutes) if minutes else None)


def _hm(minutes: int) -> str:

    h, m = divmod(int(minutes), 60)

    return f"{h}h{m:02d}" if h else f"{m} min"


def build(profile: str, runner, plan, activities=None) -> str:
    """Bloco de texto 'TREINO DO ATLETA' (vazio se não houver nada)."""

    lines: list[str] = []

    sessions = {s.day: s for s in plan.sessions} if plan else {}

    # --- o que o PLANO manda ----------------------------------------------
    if sessions:

        total_km = 0.0

        rows = []

        for day in nt.WEEKDAYS:

            s = sessions.get(day)

            if s is None:

                continue

            km, minutes = session_load(s)

            total_km += km or 0

            kind = nt.DAY_LABELS[nt.classify_day(s, _kind)]

            size = " · ".join(
                x for x in (
                    f"{km:g} km" if km else "",
                    f"~{_hm(minutes)}" if minutes else "",
                ) if x
            )

            rows.append(
                f"- {nt.DAY_PT[day]}: {kind} ({s.workout_type})"
                f"{' — ' + size if size else ''}"
            )

        lines.append(
            f"Plano da semana: {len(rows)} treino(s) de corrida por semana, "
            f"~{total_km:.0f} km no total."
        )

        lines += rows

        rest = [nt.DAY_PT[d] for d in nt.WEEKDAYS if d not in sessions]

        if rest:

            lines.append("Dias sem corrida: " + ", ".join(rest) + ".")

    # --- o que ele FAZ de verdade (histórico) -----------------------------
    try:

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.application.history.runner_baseline_builder import (
            RunnerBaselineBuilder,
        )
        from app.infrastructure.persistence.activity_archive_repository import (
            ActivityArchiveRepository,
        )

        acts = activities or ActivityArchiveRepository().load_activities(profile)

        base = RunnerBaselineBuilder.build(
            AthleteDossier._archive_history(acts), runner
        )

        if base.has_history:

            lines.append(
                f"Na prática (últimas semanas): ~{base.runs_per_week:.1f} "
                f"corridas/semana, ~{base.weekly_km:.0f} km/semana (melhor "
                f"semana {base.max_week_km:.0f} km), corrida típica "
                f"~{base.typical_run_km:.1f} km, maior treino recente "
                f"~{base.longest_km:.1f} km, volume {base.trend}."
            )

    except Exception as e:

        print(f"Nutrição: histórico de treino falhou p/ '{profile}': {e}")

    # --- outros treinos ---------------------------------------------------
    extra = getattr(runner, "strength_training_days", None)

    if extra:

        lines.append(
            "Faz musculação/fortalecimento também: " + ", ".join(extra) + "."
        )

    return "\n".join(lines)
