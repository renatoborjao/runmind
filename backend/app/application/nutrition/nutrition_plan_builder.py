"""Monta o PLANO ALIMENTAR do atleta: metas por dia (determinístico, a partir da
bioimpedância + plano de treino real) + cardápio de 7 dias feito pela IA com o
dossiê completo do atleta como contexto ([[feedback_base_historico_sempre]])."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from google.genai import types

from app.application.coach.context.athlete_dossier import (
    COACH_MIND,
    EVOLUTION,
    AthleteDossier,
)
from app.application.home.home_summary_builder import _kind, planned_km
from app.application.nutrition import nutrition_targets as nt
from app.core.clock import today_local, use_athlete_timezone
from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)
from app.infrastructure.persistence.nutrition_repository import (
    NutritionRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

MAX_OUTPUT_TOKENS = 16000

_MACROS = ("kcal", "protein_g", "carb_g", "fat_g")

# desvio aceito do total do dia vs a meta de kcal antes da passada de ajuste
MAX_DEVIATION = 0.08

PROMPT = """Você é o nutricionista esportivo do Ritmind, o app de corrida. \
Monte o CARDÁPIO de 7 dias deste atleta, em português do Brasil, com comida \
brasileira comum e acessível (arroz, feijão, ovo, frango, tapioca, frutas, \
pão, aveia, iogurte, batata-doce etc.), porções em medidas caseiras + gramas.

{dossier}

▸ COMPOSIÇÃO CORPORAL (bioimpedância)
{body}

▸ PREFERÊNCIAS
Objetivo: {goal}
Refeições por dia: {meals}
Restrições/alergias/intolerâncias: {restrictions}
Não gosta / não come: {dislikes}

▸ METAS POR DIA (já calculadas — o cardápio de cada dia deve bater nelas, \
±5%)
{targets}

REGRAS:
- Cada dia segue a meta do SEU dia de treino. Dia de longão/treino forte: \
carbo mais alto, refeição pré-treino (1–3h antes) e pós-treino (até 1h \
depois, com proteína + carbo). Descanso: mais leve em carbo, mesma proteína.
- Se houver treino no dia, marque a refeição pré e pós com "tag": \
"pre_treino" / "pos_treino"; as demais "tag": null.
- Respeite RIGOROSAMENTE restrições e o que ele não come.
- Varie os alimentos entre os dias (não repita o mesmo cardápio 7 vezes), \
mas mantenha praticidade (sobras do jantar viram almoço etc.).
- Some os macros de cada refeição com cuidado: o total do dia deve fechar com \
a meta.
- "note": 1 frase curta do dia (ex.: "longão amanhã: jantar com mais carbo"). \
"tips": 3 a 5 dicas gerais curtas (hidratação, sódio, gel no longão…), \
personalizadas.

Responda APENAS com JSON:
{{"days": [{{"day": "Monday", "meals": [{{"name": "Café da manhã", \
"time": "07:00", "tag": null, "items": [{{"food": "Ovo mexido", \
"qty": "2 unidades (100 g)"}}], "kcal": 0, "protein_g": 0, "carb_g": 0, \
"fat_g": 0}}], "note": "..."}}], "tips": ["..."]}}
Os 7 dias em ordem: Monday…Sunday."""


def _num(v) -> float | None:

    try:

        return float(v)

    except (TypeError, ValueError):

        return None


def _validate(data) -> dict | None:
    """Estrutura mínima + totais recalculados pela soma das refeições (número
    é soma, não o que o modelo disse)."""

    if not isinstance(data, dict):

        return None

    days_in = data.get("days")

    if not isinstance(days_in, list) or len(days_in) < 7:

        return None

    by_day: dict[str, dict] = {}

    for d in days_in:

        if not isinstance(d, dict) or d.get("day") not in nt.WEEKDAYS:

            continue

        meals = []

        for m in d.get("meals") or []:

            if not isinstance(m, dict) or not m.get("items"):

                continue

            items = []

            for i in m["items"]:

                if not isinstance(i, dict) or not str(i.get("food", "")).strip():

                    continue

                items.append({
                    "food": str(i.get("food", "")).strip(),
                    "qty": str(i.get("qty", "")).strip(),
                    "kcal": round(_num(i.get("kcal")) or 0),
                    "protein_g": round(_num(i.get("protein_g")) or 0),
                    "carb_g": round(_num(i.get("carb_g")) or 0),
                    "fat_g": round(_num(i.get("fat_g")) or 0),
                })

            if not items:

                continue

            meals.append({
                "name": str(m.get("name", "Refeição")).strip(),
                "time": str(m.get("time") or "").strip(),
                "tag": m.get("tag")
                if m.get("tag") in ("pre_treino", "pos_treino")
                else None,
                "items": items,
                **{k: sum(i[k] for i in items) for k in _MACROS},
            })

        if len(meals) < 3:

            return None

        by_day[d["day"]] = {
            "day": d["day"],
            "meals": meals,
            "note": str(d.get("note") or "").strip(),
            "totals": {
                k: sum(m[k] for m in meals) for k in _MACROS
            },
        }

    if len(by_day) < 7:

        return None

    tips = [str(t).strip() for t in (data.get("tips") or []) if str(t).strip()]

    return {"days": [by_day[d] for d in nt.WEEKDAYS], "tips": tips[:6]}


def _parse(raw: str) -> dict | None:

    try:

        return _validate(json.loads(repair_json(raw)))

    except (json.JSONDecodeError, TypeError, ValueError):

        return None


# um plano por mês, e só com bioimpedância nova (senão gera a toa, e gasta IA)
PLAN_COOLDOWN_DAYS = 30


def eligibility(data: dict, today: date) -> dict:
    """Pode gerar plano agora? {allowed, reason, next_date}. Libera se ainda
    não há plano; depois só com leitura NOVA (mais recente que a do plano) e
    30 dias desde o último plano."""

    plan = data.get("plan")

    if not plan:

        return {"allowed": True, "reason": None, "next_date": None}

    reading = latest_reading(data) or {}

    last_reading = plan.get("reading_date")

    try:

        next_date = date.fromisoformat(plan["generated_on"]) + timedelta(
            days=PLAN_COOLDOWN_DAYS
        )

    except (KeyError, ValueError, TypeError):

        next_date = today

    has_new = bool(
        reading.get("date") and reading.get("date") != last_reading
        and (not last_reading or reading["date"] > last_reading)
    )

    if not has_new:

        return {
            "allowed": False,
            "reason": "Seu plano é feito em cima de uma bioimpedância. Registre "
            "uma nova medição pra gerar o próximo.",
            "next_date": next_date.isoformat() if today < next_date else None,
        }

    if today < next_date:

        return {
            "allowed": False,
            "reason": "Um novo plano sai a cada 30 dias, com bioimpedância "
            f"nova. Você libera em {next_date.strftime('%d/%m/%Y')}.",
            "next_date": next_date.isoformat(),
        }

    return {"allowed": True, "reason": None, "next_date": None}


def latest_reading(data: dict) -> dict | None:

    readings = data.get("readings") or []

    return readings[-1] if readings else None


class NutritionPlanBuilder:

    @staticmethod
    def targets(profile: str) -> dict | None:
        """Metas dos 7 dias (sem cardápio) — None se não há peso confiável."""

        repo = NutritionRepository().load(profile)

        runner = RunnerProfileRepository().load(profile)

        use_athlete_timezone(getattr(runner, "timezone", None))

        reading = latest_reading(repo) or {}

        weight = reading.get("weight_kg") or getattr(runner, "weight", None)

        if not weight:

            return None

        goal = repo["settings"].get("goal") or "performance"

        bmr, method = nt.compute_bmr(
            weight=weight,
            height_cm=getattr(runner, "height", 0) or 170,
            age=getattr(runner, "age", 0) or 30,
            sex=getattr(runner, "sex", None),
            bmr_device=reading.get("bmr_kcal"),
            lean_mass=reading.get("lean_mass_kg"),
        )

        plan = WeeklyPlanRepository().load(profile)

        sessions = {s.day: s for s in plan.sessions} if plan else {}

        days = []

        for day in nt.WEEKDAYS:

            s = sessions.get(day)

            day_type = nt.classify_day(s, _kind)

            t = nt.day_targets(
                goal=goal,
                weight=weight,
                bmr=bmr,
                train_kcal=nt.training_kcal(s, weight, planned_km),
                day_type=day_type,
            )

            workout = (
                (getattr(s, "objective", None) or getattr(s, "workout_type", None))
                if s
                else None
            )

            days.append({
                "day": day,
                "day_pt": nt.DAY_PT[day],
                "type": day_type,
                "type_pt": nt.DAY_LABELS[day_type],
                "workout": workout,
                **t,
            })

        return {
            "goal": goal,
            "goal_pt": nt.GOALS.get(goal, goal),
            "weight_kg": round(weight, 1),
            "bmr_kcal": round(bmr),
            "bmr_method": method,
            "days": days,
        }

    @staticmethod
    def _off_days(menu: dict, targets: dict) -> list[str]:
        """Dias cujo total real (soma dos itens) foge da meta de kcal."""

        out = []

        for d, t in zip(menu["days"], targets["days"]):

            gap = (d["totals"]["kcal"] - t["kcal"]) / t["kcal"]

            if abs(gap) > MAX_DEVIATION:

                out.append(
                    f"{d['day']}: total {d['totals']['kcal']} kcal, meta "
                    f"{t['kcal']} kcal ({gap * 100:+.0f}%)"
                )

        return out

    @staticmethod
    async def _adjust(menu: dict, targets: dict) -> dict:
        """Uma passada de correção: manda os dias fora da meta de volta pra IA
        mexer nas PORÇÕES (não nos números). Melhor esforço — se falhar ou
        piorar, fica o cardápio original com os totais reais, honestos."""

        off = NutritionPlanBuilder._off_days(menu, targets)

        if not off:

            return menu

        nl = chr(10)

        prompt = (
            "Este cardápio de 7 dias tem dias fora da meta de calorias:" + nl
            + nl.join(off)
            + nl + nl + "Ajuste as PORÇÕES (gramas/medidas) dos itens desses "
            "dias pra o total real ficar dentro de ±5% da meta, recalculando "
            "kcal/proteína/carbo/gordura de CADA ITEM pela composição real. "
            "Não fabrique número pra fechar conta. Devolva o JSON COMPLETO "
            "dos 7 dias, mesmo formato, dias já corretos inalterados." + nl + nl
            + json.dumps(
                {"days": [
                    {"day": d["day"], "note": d["note"], "meals": d["meals"]}
                    for d in menu["days"]
                ], "tips": menu["tips"]},
                ensure_ascii=False,
            )
        )

        try:

            fixed = await generate_json(
                model=get_settings().gemini_coach_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
                parse=_parse,
                attempts=2,
            )

        except Exception as e:

            print(f"Ajuste de porções do cardápio falhou: {e}")

            return menu

        if fixed is None:

            return menu

        before = len(off)

        after = len(NutritionPlanBuilder._off_days(fixed, targets))

        return fixed if after <= before else menu

    @staticmethod
    async def generate(profile: str) -> dict | None:
        """Gera e PERSISTE o plano (metas + cardápio). None se não há base
        (sem peso) ou a IA falhou — quem chama avisa o atleta."""

        targets = NutritionPlanBuilder.targets(profile)

        if targets is None:

            return None

        data = NutritionRepository().load(profile)

        settings = data["settings"]

        reading = latest_reading(data)

        runner = RunnerProfileRepository().load(profile)

        dossier = AthleteDossier.render(
            profile, runner=runner, exclude=(EVOLUTION, COACH_MIND)
        )

        body = (
            "\n".join(
                f"- {k}: {v}"
                for k, v in (reading or {}).items()
                if v is not None and k != "source"
            )
            or f"Sem bioimpedância — só peso {targets['weight_kg']} kg."
        )

        tgt = "\n".join(
            f"- {d['day']} ({d['day_pt']}, {d['type_pt']}"
            f"{', ' + d['workout'] if d['workout'] else ''}): "
            f"{d['kcal']} kcal | P {d['protein_g']} g | C {d['carb_g']} g | "
            f"G {d['fat_g']} g"
            for d in targets["days"]
        )

        prompt = PROMPT.format(
            dossier=dossier,
            body=body,
            goal=targets["goal_pt"],
            meals=settings.get("meals_per_day") or 5,
            restrictions=settings.get("restrictions") or "nenhuma informada",
            dislikes=settings.get("dislikes") or "nenhum informado",
            targets=tgt,
        )

        try:

            menu = await generate_json(
                model=get_settings().gemini_coach_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
                parse=_parse,
            )

        except Exception as e:

            print(f"Falha ao gerar cardápio de '{profile}': {e}")

            return None

        if menu is None:

            return None

        menu = await NutritionPlanBuilder._adjust(menu, targets)

        plan = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_on": today_local().isoformat(),
            "reading_date": (reading or {}).get("date"),
            "targets": targets,
            "menu": menu,
        }

        data["plan"] = plan

        NutritionRepository().save(profile, data)

        return plan
