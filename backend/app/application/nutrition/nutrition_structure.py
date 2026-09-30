"""A ESTRUTURA do plano alimentar, toda determinística (número é número).

Molde do plano de nutricionista ("Distribuição de Porções Diárias para X
kcal"): UM dia-base em kcal, repartido por refeição; a IA só preenche comida e
porção em cima destes alvos.

- TIERS: metas dos tipos de dia (descanso / treino / longão) tiradas do plano
  de treino real. O dia-base é o de TREINO (inclui pré-treino); no descanso
  tira-se o pré, no longão entra o durante + jantar reforçado.
- REFEIÇÕES: o dia-base repartido (pré-treino + café, almoço, lanche, jantar,
  ceia conforme quantas refeições o atleta quer).
- TABELA DO LONGÃO: carbo por hora conforme a duração (recomendação esportiva
  padrão)."""

from __future__ import annotations

PRE_SHARE = 0.08

# (nome, horário padrão, fração do dia-base) por nº de refeições PRINCIPAIS;
# o pré-treino (8%) vem além delas e as frações somam 92%
_MEAL_SETS = {
    3: [("Café da manhã", "08:00", .27), ("Almoço", "12:30", .37),
        ("Jantar", "19:30", .28)],
    4: [("Café da manhã", "08:00", .23), ("Almoço", "12:30", .32),
        ("Lanche da tarde", "16:00", .14), ("Jantar", "19:30", .23)],
    5: [("Café da manhã", "08:00", .21), ("Almoço", "12:30", .30),
        ("Lanche da tarde", "16:00", .13), ("Jantar", "19:30", .21),
        ("Ceia", "21:30", .07)],
    6: [("Café da manhã", "08:00", .19), ("Lanche da manhã", "10:30", .08),
        ("Almoço", "12:30", .28), ("Lanche da tarde", "16:00", .12),
        ("Jantar", "19:30", .20), ("Ceia", "21:30", .05)],
}

# tabela de porções (sistema de equivalentes usado por nutricionistas no
# Brasil): grupo → kcal por porção. Entra no prompt pra IA somar certo.
PORTIONS = [
    ("Frutas", 50, "1 banana média (80 g), 1 fatia de mamão (150 g)"),
    ("Carboidratos (pães, biscoitos, tapioca, aveia)", 60,
     "1 fatia de pão integral, 2 col. sopa de goma de tapioca (30 g), "
     "1 col. sopa de aveia (15 g)"),
    ("Carboidratos (arroz, massas, cereais, tubérculos)", 70,
     "2 col. sopa de arroz cozido (40 g), 50 g de macarrão cozido, "
     "100 g de batata-doce"),
    ("Proteína animal (carnes e ovos)", 100,
     "1 ovo, 60 g de frango/carne magra/peixe cozido"),
    ("Proteína animal (laticínios)", 120,
     "1 iogurte natural desnatado (170 g), 30 g de queijo branco"),
    ("Proteína vegetal (leguminosas)", 70, "1 concha média de feijão (100 g)"),
    ("Suplemento proteico", 120, "1 dose de whey (30 g)"),
    ("Doces", 100, "1 col. sopa de mel (15 g) = 1/2 porção"),
    ("Gorduras boas", 70, "1 col. sopa de azeite (8 ml), 3 castanhas"),
    ("Hortaliças I e II", 0, "à vontade (salada e legumes cozidos)"),
]

# carbo DURANTE o treino por faixa de duração (g/h) — recomendação esportiva
LONG_RUN_FUELING = [
    {"faixa": "até 60 min", "min": 0, "max": 60, "carb_h": "—",
     "nota": "Só água; carbo durante não é necessário."},
    {"faixa": "60 a 90 min", "min": 60, "max": 90, "carb_h": "~30 g/h",
     "nota": "Comece por volta dos 40 min."},
    {"faixa": "90 a 150 min", "min": 90, "max": 150, "carb_h": "45–60 g/h",
     "nota": "Em doses a cada 20–30 min."},
    {"faixa": "mais de 150 min", "min": 150, "max": 999, "carb_h": "60–90 g/h",
     "nota": "Misture fontes (gel + fruta/isotônico) e reponha sódio."},
]

HYDRATION = "400 a 800 ml de líquido por hora de treino (mais no calor)."


def meals_for(base: dict, meals_per_day: int) -> list[dict]:
    """Refeições do dia-base (pré-treino primeiro), com a meta de kcal e
    macros de cada uma."""

    n = meals_per_day if meals_per_day in _MEAL_SETS else 4

    rows = [("Pré-treino", "", PRE_SHARE)] + _MEAL_SETS[n]

    return [
        {
            "name": name,
            "time": time,
            "kcal": round(base["kcal"] * share / 10) * 10,
            "protein_g": round(base["protein_g"] * share),
            "carb_g": round(base["carb_g"] * share),
            "fat_g": round(base["fat_g"] * share),
        }
        for name, time, share in rows
    ]


def fueling_row(duration_min: int) -> dict:

    return next(
        (r for r in LONG_RUN_FUELING if r["min"] <= duration_min < r["max"]),
        LONG_RUN_FUELING[-1],
    )


def build_tiers(day_rows: list[dict]) -> list[dict]:
    """Agrupa os 7 dias em tipos: descanso / treino / longão (só os que
    existem no plano; descanso sempre)."""

    groups: dict[str, list[dict]] = {"rest": [], "training": [], "long": []}

    for d in day_rows:

        key = {"rest": "rest", "long": "long"}.get(d["type"], "training")

        groups[key].append(d)

    labels = {
        "rest": "Dia de descanso",
        "training": "Dia de treino",
        "long": "Longão / treino forte",
    }

    tiers = []

    for key in ("rest", "training", "long"):

        rows = groups[key]

        if not rows:

            continue

        n = len(rows)

        tiers.append({
            "key": key,
            "label": labels[key],
            "days_pt": [r["day_pt"] for r in rows],
            "workouts": [r["workout"] for r in rows if r.get("workout")],
            "distance_km": max((r.get("distance_km") or 0 for r in rows), default=0),
            "duration_min": max((r.get("duration_min") or 0 for r in rows), default=0),
            "kcal": round(sum(r["kcal"] for r in rows) / n / 10) * 10,
            "protein_g": round(sum(r["protein_g"] for r in rows) / n),
            "carb_g": round(sum(r["carb_g"] for r in rows) / n),
            "fat_g": round(sum(r["fat_g"] for r in rows) / n),
        })

    return tiers


def base_tier(tiers: list[dict]) -> dict:
    """O dia-base do plano: o dia de TREINO (o mais típico de quem corre);
    sem ele, o longão; sem treino nenhum, o descanso."""

    by_key = {t["key"]: t for t in tiers}

    return by_key.get("training") or by_key.get("long") or by_key["rest"]
