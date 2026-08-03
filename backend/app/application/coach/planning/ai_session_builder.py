"""Traduz uma sessão que a IA emitiu (campos soltos: workout_type,
distance_km, pace_min...) num dict compatível com PlannedSession, pronto pra
virar operação de proposta. Fonte única usada pela troca de aversão e pelo
re-plano do 'furou-ontem' — os steps ficam no formato cru da IA (o applier
reidrata com parse_steps)."""


def build_session_dict(day: str, kind: str, raw: dict) -> dict | None:

    workout_type = str(raw.get("workout_type", "")).strip()

    if not workout_type:

        return None

    distance = raw.get("distance_km")

    duration = raw.get("duration_min")

    structure = raw.get("structure")

    if isinstance(structure, list):

        structure = "\n".join(
            str(step).strip() for step in structure if str(step).strip()
        )

    else:

        structure = str(structure or "").strip()

    purpose = str(raw.get("purpose", "")).strip()

    return {
        "day": day,
        "workout_type": workout_type,
        "objective": purpose,
        "planned_distance_km": (
            round(float(distance), 1)
            if isinstance(distance, (int, float)) and distance > 0
            else None
        ),
        # sessão por TEMPO (quando o atleta prefere/pede minutos, não km): a
        # IA emite duration_min e a sessão fica sem distância. Ver
        # [[project_tudo_dinamico]].
        "planned_duration_minutes": (
            int(round(float(duration)))
            if isinstance(duration, (int, float)) and duration > 0
            else None
        ),
        "target_pace_min": _pace(raw.get("pace_min")),
        "target_pace_max": _pace(raw.get("pace_max")),
        "kind": kind,
        "structure": structure,
        "purpose": purpose,
        "steps": raw.get("steps") or [],
    }


def _pace(value) -> str | None:

    return str(value).strip() if value else None
