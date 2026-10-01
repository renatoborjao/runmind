"""Monta o PLANO ALIMENTAR do atleta no molde de um plano de nutricionista:
UM dia-base em kcal, repartido por refeição (alimentos × porções × grupo ×
kcal, com alternativas "ou"), mais ajustes pra descanso/longão e orientações.

Metas e estrutura são determinísticas (nutrition_targets/nutrition_structure,
a partir da bioimpedância + plano de treino real); a IA preenche comida e
porção com o dossiê do atleta como contexto ([[feedback_base_historico_sempre]])
e nunca decide número."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from google.genai import types

from app.application.coach.context.athlete_dossier import (
    CAPACITY,
    EVOLUTION,
    PATTERNS,
    PERCEPTION,
    PLAN_WEEK,
    AthleteDossier,
)
from app.application.home.home_summary_builder import _kind, planned_km
from app.application.nutrition import nutrition_structure as ns
from app.application.nutrition import nutrition_targets as nt
from app.application.nutrition import training_profile
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

MAX_OUTPUT_TOKENS = 8000

# desvio aceito do total do dia vs o dia-base antes de pedir nova passada
MAX_DEVIATION = 0.10

# uma atualização (medição + plano) por mês — a IA custa e o corpo não muda em dias
PLAN_COOLDOWN_DAYS = 30

PROMPT = """Você é o nutricionista esportivo do Ritmind, o app de corrida. \
Monte o PLANO ALIMENTAR deste atleta no formato de um plano de nutricionista: \
"Distribuição de porções diárias para {base_kcal} kcal" — UM dia-base dividido \
em refeições; cada refeição é uma tabela de alimentos com nº de porções, grupo \
alimentar e kcal, com alternativas ("ou") pra ele escolher. Português do \
Brasil, comida brasileira comum e acessível, medidas caseiras + gramas.

{dossier}

▸ TREINO DO ATLETA (o que o plano manda + o que ele faz de verdade)
{training}

▸ COMPOSIÇÃO CORPORAL (bioimpedância)
{body}

▸ PREFERÊNCIAS
Objetivo(s): {goal}
Peso-alvo: {target}
Restrições/alergias/intolerâncias: {restrictions}
Não gosta / não come: {dislikes}

▸ METAS (já calculadas — você preenche comida e porção, não decide número)
Dia-base (dia de treino): {base_kcal} kcal | P {base_p} g | C {base_c} g | \
G {base_f} g
Alvo por refeição (kcal | proteína):
{meals}
Outros tipos de dia (o dia-base se adapta a eles nos "ajustes"):
{tiers}

▸ TABELA DE PORÇÕES (kcal por porção — use ela pra somar)
{portions}

▸ TABELA DO LONGÃO (carbo durante o treino, por duração)
{fueling}
Maior treino planejado dele: ~{long_min} min.

COMO TRABALHAR:
1. A soma das kcal das refeições (uma opção de cada) fecha o dia-base ±5%, \
cada refeição fica a ±10% do seu alvo, e a proteína do dia não passa da meta \
(passar estoura as calorias). Faça a conta ao escrever: kcal da linha = \
porções × kcal da porção do grupo.
2. Cada linha: "alimentos" (o item + alternativas equivalentes com "ou", \
quantidade em medida caseira e gramas), "porcoes" (número, aceita 1/2), \
"grupo" e "kcal". Salada e legumes cozidos: porcoes "à vontade", kcal 0.
3. A medida escrita tem que bater com as porções: "porcoes" × porção do grupo = a quantidade do alimento (3 porções de gorduras boas = 3 col. de azeite ou 9 castanhas, não "3 castanhas"). As alternativas do "ou" valem o MESMO nº de porções. Revise a ortografia dos alimentos.
3b. Alternativas de verdade no "ou" (frango ou carne magra ou tilápia; pão ou \
tapioca ou cuscuz) — é assim que ele varia durante a semana sem sair do \
plano. Só combinações que um brasileiro de fato come.
4. Pré-treino: leve, carbo de fácil digestão, pouca gordura e fibra; \
"horario" "1 a 2 h antes do treino". Lanche da tarde (se existir) tem 2 \
opções equivalentes (uma doce, uma salgada); as demais refeições têm 1 opção.
5. "orientacao" de cada refeição: 2 a 3 frases, voz de nutricionista próxima, \
baseada no que você viu dele (treino, corpo, sono) — não genérica.
6. "durante_treino": 1 a 2 frases com a conduta em cima da TABELA DO LONGÃO e \
da duração do maior treino dele (cite quantidades: sachê/gel, fruta, água).
7. "ajustes": "descanso" (o que tirar do dia-base pra chegar na meta do descanso: liste por refeição, em PORÇÕES da tabela e kcal, e a soma tem que bater com a diferença de kcal entre os tipos de dia) e "longao" (jantar da véspera com mais carbo — quantidades em porções e gramas — e o que mudar na refeição pós-treino).
8. "orientacoes": 6 a 8 orientações gerais curtas e práticas (consistência, \
hidratação, carbo não é vilão, fim de semana, ajuste se mudar a rotina).
9. Respeite RIGOROSAMENTE restrições e o que ele não come.

Responda APENAS com JSON:
{{"refeicoes": [{{"nome": "Pré-treino", "horario": "1 a 2 h antes do treino", \
"opcoes": [{{"titulo": null, "linhas": [{{"alimentos": "1 banana (80 g)", \
"porcoes": "1", "grupo": "Frutas", "kcal": 50}}], "substituicao": null}}], \
"orientacao": "..."}}], "durante_treino": "...", "ajustes": {{"descanso": \
"...", "longao": "..."}}, "orientacoes": ["..."]}}"""


def _num(v) -> float | None:

    try:

        return float(v)

    except (TypeError, ValueError):

        return None


def _text(v) -> str:

    return str(v).strip() if v is not None else ""


def _validate(data) -> dict | None:
    """Estrutura mínima + kcal recalculados por SOMA das linhas (número é
    soma, não o que o modelo disse)."""

    if not isinstance(data, dict):

        return None

    meals = []

    for m in data.get("refeicoes") or []:

        if not isinstance(m, dict) or not _text(m.get("nome")):

            continue

        options = []

        for o in m.get("opcoes") or []:

            if not isinstance(o, dict):

                continue

            rows = []

            for r in o.get("linhas") or []:

                if not isinstance(r, dict) or not _text(r.get("alimentos")):

                    continue

                rows.append({
                    "alimentos": _text(r.get("alimentos")),
                    "porcoes": _text(r.get("porcoes")) or "—",
                    "grupo": _text(r.get("grupo")),
                    "kcal": round(_num(r.get("kcal")) or 0),
                })

            if len(rows) < 1:

                continue

            options.append({
                "titulo": _text(o.get("titulo")) or None,
                "linhas": rows,
                "substituicao": _text(o.get("substituicao")) or None,
                "kcal": sum(r["kcal"] for r in rows),
            })

        if not options:

            continue

        meals.append({
            "nome": _text(m.get("nome")),
            "horario": _text(m.get("horario")),
            "opcoes": options,
            "orientacao": _text(m.get("orientacao")),
            # o total do dia conta UMA opção por refeição (a média delas)
            "kcal": round(sum(o["kcal"] for o in options) / len(options)),
        })

    if len(meals) < 4:

        return None

    adj = data.get("ajustes") if isinstance(data.get("ajustes"), dict) else {}

    return {
        "refeicoes": meals,
        "durante_treino": _text(data.get("durante_treino")),
        "ajustes": {
            "descanso": _text(adj.get("descanso")),
            "longao": _text(adj.get("longao")),
        },
        "orientacoes": [
            _text(t) for t in (data.get("orientacoes") or []) if _text(t)
        ][:10],
        "total_kcal": sum(m["kcal"] for m in meals),
    }


def _parse(raw: str) -> dict | None:

    try:

        return _validate(json.loads(repair_json(raw)))

    except (json.JSONDecodeError, TypeError, ValueError):

        return None


def settings_goals(settings: dict) -> list[str]:
    """Objetivos escolhidos (lista); aceita o formato antigo (`goal`)."""

    goals = settings.get("goals") or (
        [settings["goal"]] if settings.get("goal") else []
    )

    goals = [g for g in goals if g in nt.GOALS]

    return goals or ["performance"]


def latest_reading(data: dict) -> dict | None:

    readings = data.get("readings") or []

    return readings[-1] if readings else None


def eligibility(data: dict, today: date) -> dict:
    """Pode registrar medição / gerar plano agora? {allowed, reason,
    next_date}. UMA atualização a cada 30 dias, sempre — vale igual pra foto e
    pra dados manuais (registrar a medição é o que atualiza o plano). Sem plano
    ainda: liberado. Se a geração falhou depois de salvar a medição, o plano
    segue sem existir e dá pra tentar de novo."""

    plan = data.get("plan")

    if not plan:

        return {"allowed": True, "reason": None, "next_date": None}

    try:

        next_date = date.fromisoformat(plan["generated_on"]) + timedelta(
            days=PLAN_COOLDOWN_DAYS
        )

    except (KeyError, ValueError, TypeError):

        return {"allowed": True, "reason": None, "next_date": None}

    if today < next_date:

        return {
            "allowed": False,
            "reason": "A bioimpedância e o plano alimentar atualizam 1 vez por "
            f"mês. Sua próxima atualização libera em "
            f"{next_date.strftime('%d/%m/%Y')}.",
            "next_date": next_date.isoformat(),
        }

    return {"allowed": True, "reason": None, "next_date": None}


class NutritionPlanBuilder:

    @staticmethod
    def targets(profile: str) -> dict | None:
        """Metas e estrutura (tipos de dia, dia-base, refeições) — None se não
        há peso confiável."""

        repo = NutritionRepository().load(profile)

        runner = RunnerProfileRepository().load(profile)

        use_athlete_timezone(getattr(runner, "timezone", None))

        reading = latest_reading(repo) or {}

        weight = reading.get("weight_kg") or getattr(runner, "weight", None)

        if not weight:

            return None

        settings = repo["settings"]

        goals = settings_goals(settings)

        target_weight = settings.get("target_weight_kg") or None

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
                goals=goals,
                weight=weight,
                bmr=bmr,
                train_kcal=nt.training_kcal(s, weight, planned_km),
                day_type=day_type,
            )

            km, minutes = training_profile.session_load(s)

            days.append({
                "day": day,
                "day_pt": nt.DAY_PT[day],
                "type": day_type,
                "type_pt": nt.DAY_LABELS[day_type],
                "workout": getattr(s, "workout_type", None) if s else None,
                "distance_km": km,
                "duration_min": minutes,
                **t,
            })

        tiers = ns.build_tiers(days)

        base = ns.base_tier(tiers)

        meals_per_day = int(settings.get("meals_per_day") or 4)

        return {
            "goals": goals,
            "goal_pt": " + ".join(nt.GOALS[g] for g in goals),
            "weight_kg": round(weight, 1),
            "target_weight_kg": target_weight,
            "weeks_estimate": nt.weeks_to_target(weight, target_weight),
            "bmr_kcal": round(bmr),
            "bmr_method": method,
            "days": days,
            "tiers": tiers,
            "base": {k: base[k] for k in ("key", "label", "kcal", "protein_g", "carb_g", "fat_g")},
            "meals": ns.meals_for(base, meals_per_day),
            "fueling": [
                {k: r[k] for k in ("faixa", "carb_h", "nota")}
                for r in ns.LONG_RUN_FUELING
            ],
            "hydration": ns.HYDRATION,
            "long_minutes": max(
                (t["duration_min"] for t in tiers if t["key"] == "long"),
                default=0,
            ),
        }

    @staticmethod
    def _prompt(profile: str, targets: dict, data: dict, feedback: str) -> str:

        settings = data["settings"]

        reading = latest_reading(data)

        runner = RunnerProfileRepository().load(profile)

        # o dossiê entra só com o que serve à mesa (quem é, corpo/recuperação
        # e o que o coach já sabe: lesões, restrições ditas no chat). O treino
        # vai no bloco estruturado.
        dossier = AthleteDossier.render(
            profile,
            runner=runner,
            exclude=(CAPACITY, EVOLUTION, PERCEPTION, PATTERNS, PLAN_WEEK),
        )

        training = training_profile.build(
            profile, runner, WeeklyPlanRepository().load(profile)
        ) or "Sem plano de treino definido."

        body = (
            "\n".join(
                f"- {k}: {v}"
                for k, v in (reading or {}).items()
                if v is not None and k != "source"
            )
            or f"Sem bioimpedância — só peso {targets['weight_kg']} kg."
        )

        long_min = targets["long_minutes"] or 75

        base = targets["base"]

        prompt = PROMPT.format(
            dossier=dossier,
            training=training,
            body=body,
            goal=targets["goal_pt"],
            target=(
                f"{targets['target_weight_kg']} kg (hoje {targets['weight_kg']}"
                f" kg, ~{targets['weeks_estimate']} semanas em ritmo saudável)"
                if targets.get("target_weight_kg") and targets.get("weeks_estimate")
                else "não definido"
            ),
            restrictions=settings.get("restrictions") or "nenhuma informada",
            dislikes=settings.get("dislikes") or "nenhum informado",
            base_kcal=base["kcal"],
            base_p=base["protein_g"],
            base_c=base["carb_g"],
            base_f=base["fat_g"],
            meals="\n".join(
                f"- {m['name']}: {m['kcal']} kcal | P {m['protein_g']} g"
                for m in targets["meals"]
            ),
            tiers="\n".join(
                f"- {t['label']} ({', '.join(t['days_pt'])}"
                f"{', ~' + str(t['duration_min']) + ' min' if t['duration_min'] else ''}"
                f"): {t['kcal']} kcal | P {t['protein_g']} g | C {t['carb_g']} g"
                for t in targets["tiers"]
            ),
            portions="\n".join(
                f"- {g}: {k} kcal/porção (ex.: {ex})" for g, k, ex in ns.PORTIONS
            ),
            fueling="\n".join(
                f"- {r['faixa']}: {r['carb_h']} — {r['nota']}"
                for r in ns.LONG_RUN_FUELING
            ) + f"\nHidratação: {ns.HYDRATION}",
            long_min=long_min,
        )

        return prompt + (f"\n\n{feedback}" if feedback else "")

    @staticmethod
    async def generate(profile: str) -> dict | None:
        """Gera e PERSISTE o plano. None se não há base (sem peso) ou a IA
        falhou — quem chama avisa o atleta. Se a soma do dia foge do dia-base,
        pede UMA nova passada ajustando porções e fica com a mais próxima."""

        targets = NutritionPlanBuilder.targets(profile)

        if targets is None:

            return None

        data = NutritionRepository().load(profile)

        base_kcal = targets["base"]["kcal"]

        best: dict | None = None

        feedback = ""

        for _ in range(2):

            try:

                menu = await generate_json(
                    model=get_settings().gemini_coach_model,
                    contents=NutritionPlanBuilder._prompt(
                        profile, targets, data, feedback
                    ),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=MAX_OUTPUT_TOKENS,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                    parse=_parse,
                )

            except Exception as e:

                print(f"Falha ao gerar plano alimentar de '{profile}': {e}")

                menu = None

            if menu is not None and (
                best is None
                or abs(menu["total_kcal"] - base_kcal)
                < abs(best["total_kcal"] - base_kcal)
            ):

                best = menu

            if best is not None and (
                abs(best["total_kcal"] - base_kcal) / base_kcal <= MAX_DEVIATION
            ):

                break

            if best is not None:

                feedback = (
                    f"ATENÇÃO: na tentativa anterior a soma do dia deu "
                    f"{best['total_kcal']} kcal, mas o dia-base é {base_kcal} "
                    "kcal. Refaça ajustando as PORÇÕES (não os números) pra "
                    "fechar o dia-base ±5%."
                )

        if best is None:

            return None

        reading = latest_reading(data) or {}

        plan = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_on": today_local().isoformat(),
            "reading_date": reading.get("date"),
            "targets": targets,
            "menu": best,
        }

        data["plan"] = plan

        NutritionRepository().save(profile, data)

        return plan
