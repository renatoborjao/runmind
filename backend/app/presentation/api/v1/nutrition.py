import base64

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.nutrition import nutrition_targets as nt
from app.application.nutrition.body_composition_reader import (
    BodyCompositionReader,
    clean_reading,
)
from app.application.nutrition.nutrition_plan_builder import (
    NutritionPlanBuilder,
    eligibility,
    latest_reading,
)
from app.core.clock import today_local
from app.infrastructure.persistence.nutrition_repository import (
    NutritionRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/nutrition", tags=["Nutrition"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024


class PhotoIn(BaseModel):
    image: str   # data URL (data:image/...;base64,...)


class ReadingIn(BaseModel):
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    fat_mass_kg: float | None = None
    lean_mass_kg: float | None = None
    muscle_mass_kg: float | None = None
    water_pct: float | None = None
    visceral_fat: float | None = None
    bmr_kcal: float | None = None
    metabolic_age: float | None = None
    date: str | None = None
    source: str | None = None


class SettingsIn(BaseModel):
    goal: str | None = None
    meals_per_day: int | None = None
    restrictions: str | None = None
    dislikes: str | None = None


@router.get("")
async def nutrition_state(profile: str = Depends(current_profile)):
    """Tudo da aba Nutrição: leitura atual + histórico, preferências, metas dos
    7 dias (calculáveis só com peso) e o último cardápio gerado."""

    data = NutritionRepository().load(profile)

    runner = RunnerProfileRepository().load(profile)

    return {
        "goals": nt.GOALS,
        "settings": data["settings"],
        "reading": latest_reading(data),
        "readings": data["readings"][-12:],
        "profile_weight": getattr(runner, "weight", None),
        "targets": NutritionPlanBuilder.targets(profile),
        "plan": data["plan"],
        "plan_gate": eligibility(data, today_local()),
    }


@router.post("/reading/photo")
async def read_photo(body: PhotoIn, profile: str = Depends(current_profile)):
    """Lê a foto do laudo e DEVOLVE os campos pro atleta conferir — não salva."""

    head, _, b64 = body.image.partition(",")

    if not head.startswith("data:image/") or not b64:

        raise HTTPException(status_code=400, detail="Imagem inválida")

    try:

        raw = base64.b64decode(b64)

    except Exception:

        raise HTTPException(status_code=400, detail="Imagem inválida")

    if len(raw) > MAX_IMAGE_BYTES:

        raise HTTPException(status_code=413, detail="Imagem muito grande")

    mimetype = head[5:].split(";")[0]

    result = await BodyCompositionReader.read(raw, mimetype)

    if result is None:

        raise HTTPException(
            status_code=422,
            detail="Não consegui ler os números dessa foto. Tente outra mais "
            "nítida ou preencha na mão.",
        )

    return result


@router.post("/reading")
async def save_reading(body: ReadingIn, profile: str = Depends(current_profile)):

    clean = clean_reading(body.model_dump())

    if clean["weight_kg"] is None:

        raise HTTPException(status_code=400, detail="Informe o peso (kg).")

    clean["date"] = clean["date"] or today_local().isoformat()
    clean["source"] = body.source or "manual"

    repo = NutritionRepository()

    data = repo.load(profile)

    # mesma data substitui (correção); senão acrescenta
    data["readings"] = [
        r for r in data["readings"] if r.get("date") != clean["date"]
    ] + [clean]

    data["readings"].sort(key=lambda r: r.get("date") or "")

    repo.save(profile, data)

    return {"reading": clean, "readings": data["readings"][-12:]}


@router.put("/settings")
async def save_settings(body: SettingsIn, profile: str = Depends(current_profile)):

    repo = NutritionRepository()

    data = repo.load(profile)

    s = data["settings"]

    if body.goal is not None:

        if body.goal not in nt.GOALS:

            raise HTTPException(status_code=400, detail="Objetivo inválido")

        s["goal"] = body.goal

    if body.meals_per_day is not None:

        s["meals_per_day"] = max(3, min(6, body.meals_per_day))

    if body.restrictions is not None:

        s["restrictions"] = body.restrictions.strip()[:400]

    if body.dislikes is not None:

        s["dislikes"] = body.dislikes.strip()[:400]

    repo.save(profile, data)

    return {"settings": s, "targets": NutritionPlanBuilder.targets(profile)}


@router.post("/plan")
async def generate_plan(profile: str = Depends(current_profile)):
    """Gera (ou refaz) o plano alimentar: metas + cardápio de 7 dias."""

    if NutritionPlanBuilder.targets(profile) is None:

        raise HTTPException(
            status_code=400,
            detail="Registre sua bioimpedância (ou ao menos o peso) primeiro.",
        )

    gate = eligibility(NutritionRepository().load(profile), today_local())

    if not gate["allowed"]:

        raise HTTPException(status_code=429, detail=gate["reason"])

    plan = await NutritionPlanBuilder.generate(profile)

    if plan is None:

        raise HTTPException(
            status_code=502,
            detail="Não consegui montar o cardápio agora. Tente de novo em "
            "instantes.",
        )

    return plan
