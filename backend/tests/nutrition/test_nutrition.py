"""Nutrição: metas por objetivo, estrutura (dia-base/refeições), limite mensal,
kcal honestas do plano e a nova passada quando a soma foge do dia-base."""

import asyncio
from datetime import date

from app.application.nutrition import nutrition_plan_builder as b
from app.application.nutrition import nutrition_structure as ns
from app.application.nutrition import nutrition_targets as nt
from app.application.nutrition.body_composition_reader import clean_reading


def test_recomposicao_tem_deficit_leve_e_proteina_alta():
    adj, prot = nt.blend_goals(["lose_fat", "gain_muscle"])
    assert adj == -0.05 and prot >= 2.1
    assert nt.blend_goals(["lose_fat"])[0] == -0.15
    assert nt.blend_goals(["lose_fat", "performance"])[0] <= -0.10


def test_kcal_nunca_abaixo_do_basal():
    t = nt.day_targets(
        goals=["lose_fat"], weight=70, bmr=1800, train_kcal=0, day_type="rest"
    )
    assert t["kcal"] >= 1800


def test_prazo_ate_o_peso_alvo():
    assert nt.weeks_to_target(78, 72) == 12
    assert nt.weeks_to_target(78, 80) == 8
    assert nt.weeks_to_target(78, 78.2) is None


def test_leitura_fora_do_plausivel_vira_none():
    r = clean_reading({"weight_kg": 78.4, "body_fat_pct": 99})
    assert r["weight_kg"] == 78.4 and r["body_fat_pct"] is None


def test_limite_mensal_vale_pra_qualquer_medicao():
    com_plano = {"plan": {"generated_on": "2026-09-30"}, "readings": []}
    assert b.eligibility({"plan": None}, date(2026, 9, 30))["allowed"]
    # dentro dos 30 dias: travado, mesmo com leitura nova (foto ou manual)
    nova = dict(com_plano, readings=[{"date": "2026-10-10"}])
    gate = b.eligibility(nova, date(2026, 10, 12))
    assert not gate["allowed"] and gate["next_date"] == "2026-10-30"
    assert "1 vez por mês" in gate["reason"]
    # passou o mês: libera
    assert b.eligibility(com_plano, date(2026, 10, 30))["allowed"]


def _days():
    rows = []
    for d, typ, k in zip(
        nt.WEEKDAYS,
        ["rest", "easy", "rest", "easy", "rest", "rest", "long"],
        [2100, 2700, 2100, 2600, 2100, 2100, 3000],
    ):
        rows.append({
            "day": d, "day_pt": nt.DAY_PT[d], "type": typ, "workout": None,
            "kcal": k, "protein_g": 160, "carb_g": k // 8, "fat_g": 70,
            "distance_km": 8 if typ != "rest" else None,
            "duration_min": 50 if typ == "easy" else (80 if typ == "long" else None),
        })
    return rows


def test_tiers_e_dia_base_e_refeicoes_fecham_100pct():
    tiers = ns.build_tiers(_days())
    assert [t["key"] for t in tiers] == ["rest", "training", "long"]
    base = ns.base_tier(tiers)
    assert base["key"] == "training"
    for n in (3, 4, 5, 6):
        meals = ns.meals_for(base, n)
        assert meals[0]["name"] == "Pré-treino"
        assert abs(sum(m["kcal"] for m in meals) - base["kcal"]) <= base["kcal"] * 0.03
    # sem dia de treino o dia-base cai pro longão e, sem nada, pro descanso
    assert ns.base_tier([t for t in tiers if t["key"] == "long"])["key"] == "long"
    assert ns.base_tier([t for t in tiers if t["key"] == "rest"])["key"] == "rest"


def test_tabela_do_longao_por_duracao():
    assert ns.fueling_row(45)["faixa"] == "até 60 min"
    assert ns.fueling_row(78)["faixa"] == "60 a 90 min"
    assert ns.fueling_row(200)["faixa"] == "mais de 150 min"


def _plan(kcals, extra=None):
    meals = [
        {"nome": f"R{i}", "horario": "08:00", "orientacao": "ok",
         "opcoes": [{"linhas": [{"alimentos": "x", "porcoes": "1",
                                 "grupo": "g", "kcal": k}]}]}
        for i, k in enumerate(kcals)
    ]
    data = {"refeicoes": meals, "durante_treino": "gel", "orientacoes": ["a"],
            "ajustes": {"descanso": "d", "longao": "l"}}
    data.update(extra or {})
    return data


def test_total_do_plano_e_soma_das_linhas():
    menu = b._validate(_plan([200, 600, 300, 500, 100]))
    assert menu["total_kcal"] == 1700
    assert b._validate(_plan([200, 600])) is None      # refeições demais faltando
    assert b._validate({"refeicoes": []}) is None


def test_opcoes_contam_a_media_no_total_do_dia():
    data = _plan([200, 600, 300, 500])
    data["refeicoes"][2]["opcoes"].append(
        {"linhas": [{"alimentos": "y", "porcoes": "1", "grupo": "g", "kcal": 400}]}
    )
    assert b._validate(data)["refeicoes"][2]["kcal"] == 350


def test_nova_passada_quando_a_soma_foge_e_fica_com_a_mais_proxima(monkeypatch):
    targets = {"base": {"kcal": 2200, "key": "training", "label": "x",
                        "protein_g": 1, "carb_g": 1, "fat_g": 1}}
    calls = []

    async def fake(**kw):
        calls.append(kw["contents"])
        # 1ª soma 2900 (longe), 2ª 2250 (perto)
        return kw["parse"](__import__("json").dumps(
            _plan([600, 800, 500, 1000] if len(calls) == 1 else [500, 700, 500, 550])
        ))

    monkeypatch.setattr(b, "generate_json", fake)
    monkeypatch.setattr(b.NutritionPlanBuilder, "targets", staticmethod(lambda p: targets))
    monkeypatch.setattr(b.NutritionPlanBuilder, "_prompt",
                        staticmethod(lambda p, t, d, f: "P" + f))
    saved = {}
    monkeypatch.setattr(b.NutritionRepository, "load",
                        lambda self, p: {"readings": [], "settings": {}, "plan": None})
    monkeypatch.setattr(b.NutritionRepository, "save",
                        lambda self, p, d: saved.update(d))

    plan = asyncio.run(b.NutritionPlanBuilder.generate("x"))

    assert len(calls) == 2 and "2900" in calls[1]
    assert plan["menu"]["total_kcal"] == 2250
    assert saved["plan"]["menu"]["total_kcal"] == 2250


def test_uma_passada_so_quando_ja_fecha(monkeypatch):
    targets = {"base": {"kcal": 2200, "key": "training", "label": "x",
                        "protein_g": 1, "carb_g": 1, "fat_g": 1}}
    calls = []

    async def fake(**kw):
        calls.append(1)
        return kw["parse"](__import__("json").dumps(_plan([500, 700, 500, 500])))

    monkeypatch.setattr(b, "generate_json", fake)
    monkeypatch.setattr(b.NutritionPlanBuilder, "targets", staticmethod(lambda p: targets))
    monkeypatch.setattr(b.NutritionPlanBuilder, "_prompt",
                        staticmethod(lambda p, t, d, f: "P"))
    monkeypatch.setattr(b.NutritionRepository, "load",
                        lambda self, p: {"readings": [], "settings": {}, "plan": None})
    monkeypatch.setattr(b.NutritionRepository, "save", lambda self, p, d: None)

    assert asyncio.run(b.NutritionPlanBuilder.generate("x")) is not None
    assert len(calls) == 1
