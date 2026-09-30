"""Metas de energia e macros POR DIA, ancoradas na bioimpedância + no plano de
treino real. Matemática determinística (número é número, não texto da IA); o
cardápio é que a IA monta em cima destas metas.

- BMR: da própria balança se veio no laudo; senão Katch-McArdle (massa magra)
  ou Mifflin-St Jeor (peso/altura/idade/sexo).
- Gasto do dia = BMR × fator de vida (sem treino) + custo do treino do dia
  (~1 kcal/kg/km corrido; por tempo quando não há km).
- Objetivo ajusta o total: secar (-15%, nunca abaixo do BMR), ganhar massa
  (+10%), performance/manter (0). Dia forte/longão ganha carbo; descanso leva
  menos."""

from __future__ import annotations

GOALS = {
    "lose_fat": "Perder gordura",
    "gain_muscle": "Ganhar massa muscular",
    "performance": "Performance na corrida",
    "maintain": "Manter o peso",
}

GOAL_ADJUST = {
    "lose_fat": -0.15,
    "gain_muscle": 0.10,
    "performance": 0.0,
    "maintain": 0.0,
}

PROTEIN_G_KG = {
    "lose_fat": 2.0,
    "gain_muscle": 1.9,
    "performance": 1.7,
    "maintain": 1.6,
}

# fator de atividade FORA do treino (trabalho/rotina leve)
BASE_ACTIVITY = 1.3

DAY_LABELS = {
    "rest": "Descanso",
    "easy": "Treino leve",
    "quality": "Treino forte",
    "long": "Longão",
}

WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday",
]
DAY_PT = {
    "Monday": "Segunda", "Tuesday": "Terça", "Wednesday": "Quarta",
    "Thursday": "Quinta", "Friday": "Sexta", "Saturday": "Sábado",
    "Sunday": "Domingo",
}


def compute_bmr(
    *, weight: float, height_cm: float, age: int, sex: str | None,
    bmr_device: float | None = None, lean_mass: float | None = None,
) -> tuple[float, str]:
    """(kcal, método)."""

    if bmr_device:

        return float(bmr_device), "balança"

    if lean_mass:

        return 370 + 21.6 * lean_mass, "Katch-McArdle"

    base = 10 * weight + 6.25 * height_cm - 5 * age

    if sex == "M":

        return base + 5, "Mifflin-St Jeor"

    if sex == "F":

        return base - 161, "Mifflin-St Jeor"

    return base - 78, "Mifflin-St Jeor"


def classify_day(session, kind_fn) -> str:
    """rest | easy | quality | long a partir da sessão planejada (ou None)."""

    if session is None:

        return "rest"

    kind = kind_fn(session.workout_type)

    return {"tiro": "quality", "long": "long"}.get(kind, "easy")


def training_kcal(session, weight: float, km_fn) -> float:

    if session is None:

        return 0.0

    km = km_fn(session) or getattr(session, "estimated_distance_km", None)

    if km:

        return float(km) * weight * 1.0

    minutes = getattr(session, "planned_duration_minutes", None)

    if minutes:

        return float(minutes) * weight * 0.14

    return 0.0


def day_targets(
    *, goal: str, weight: float, bmr: float, train_kcal: float, day_type: str,
) -> dict:

    tdee = bmr * BASE_ACTIVITY + train_kcal

    kcal = tdee * (1 + GOAL_ADJUST.get(goal, 0.0))

    # piso: nunca abaixo do metabolismo basal
    kcal = max(kcal, bmr)

    protein = PROTEIN_G_KG.get(goal, 1.6) * weight

    fat = (1.0 if day_type == "rest" else 0.9) * weight

    carb = (kcal - protein * 4 - fat * 9) / 4

    # carbo mínimo pra quem corre (evita prato sem energia)
    floor = 3.0 * weight if day_type in ("quality", "long") else 2.5 * weight

    if carb < floor:

        carb = floor

        fat = max(0.6 * weight, (kcal - protein * 4 - carb * 4) / 9)

        kcal = protein * 4 + carb * 4 + fat * 9

    return {
        "kcal": round(kcal / 10) * 10,
        "protein_g": round(protein),
        "carb_g": round(carb),
        "fat_g": round(fat),
        "training_kcal": round(train_kcal / 10) * 10,
    }
