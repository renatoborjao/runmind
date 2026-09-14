from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.shoes.shoe_command_engine import ShoeCommandEngine
from app.domain.entities.shoe import (
    DEFAULT_WEAR_KM,
    Shoe,
    canonical_category,
)
from app.infrastructure.persistence.shoe_repository import ShoeRepository
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/shoes", tags=["Shoes"])


def _shoe_dict(s: Shoe) -> dict:

    threshold = s.alert_threshold_km or 1

    return {
        "id": s.id,
        "name": s.name,
        "nickname": s.nickname,
        "label": s.label,
        "category": s.category,
        "is_default": s.is_default,
        "retired": s.retired,
        "total_km": s.total_km,
        "initial_km": round(s.initial_km, 1),
        "accumulated_km": round(s.accumulated_km, 1),
        "alert_threshold_km": s.alert_threshold_km,
        "pct": min(100, round(s.total_km / threshold * 100)),
        "remaining_km": round(max(0.0, s.alert_threshold_km - s.total_km), 1),
        "worn": s.total_km >= s.alert_threshold_km,
    }


def _sorted(shoes: list[Shoe]) -> list[Shoe]:
    """Ativos primeiro (o do dia a dia à frente, depois por rodagem), aposentados
    no fim."""

    active = [s for s in shoes if not s.retired]
    retired = [s for s in shoes if s.retired]

    active.sort(key=lambda s: (not s.is_default, -s.total_km))
    retired.sort(key=lambda s: -s.total_km)

    return active + retired


class ShoeIn(BaseModel):
    name: str
    nickname: str | None = None
    category: str | None = None
    initial_km: float | None = None
    alert_threshold_km: float | None = None
    is_default: bool = False


class ShoePatch(BaseModel):
    name: str | None = None
    nickname: str | None = None
    category: str | None = None
    total_km: float | None = None          # corrige o odômetro (total do par)
    alert_threshold_km: float | None = None
    is_default: bool | None = None
    retired: bool | None = None


@router.get("")
async def list_shoes(profile: str = Depends(current_profile)):
    """O armário do atleta: todos os pares (ativos + aposentados) com km, % de
    desgaste e o par em uso."""

    try:

        book = ShoeRepository().load(profile)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    return {"shoes": [_shoe_dict(s) for s in _sorted(book.shoes)]}


@router.post("")
async def add_shoe(body: ShoeIn, profile: str = Depends(current_profile)):
    """Adiciona um par ao armário."""

    name = (body.name or "").strip()

    if not name:

        raise HTTPException(status_code=422, detail="Dá um nome pro tênis.")

    repo = ShoeRepository()
    book = repo.load(profile)

    twin = ShoeCommandEngine._resolve(book, name)

    if twin is not None and not twin.retired:

        raise HTTPException(
            status_code=409, detail="Você já tem um par com esse nome no armário."
        )

    category = canonical_category(body.category) or (
        (body.category or "").strip() or None
    )

    shoe = Shoe(
        id=ShoeCommandEngine._unique_id(book, name),
        name=name,
        nickname=(body.nickname or "").strip() or None,
        category=category,
        initial_km=max(0.0, float(body.initial_km or 0.0)),
        alert_threshold_km=(
            float(body.alert_threshold_km)
            if body.alert_threshold_km and body.alert_threshold_km > 0
            else DEFAULT_WEAR_KM
        ),
        created_at=date.today().isoformat(),
    )

    shoe.wear_alerted = shoe.total_km >= shoe.alert_threshold_km

    book.shoes.append(shoe)

    # primeiro par do armário vira o do dia a dia por padrão, salvo se pediram
    # explicitamente (ou não houver nenhum default ainda)
    if body.is_default or book.default() is None:

        ShoeCommandEngine._make_default(book, shoe)

    repo.save(profile, book)

    return _shoe_dict(shoe)


@router.patch("/{shoe_id}")
async def edit_shoe(
    shoe_id: str, body: ShoePatch, profile: str = Depends(current_profile)
):
    """Edita um par: nome, apelido, categoria, odômetro (total), limiar de
    desgaste, marcar em uso ou aposentar."""

    repo = ShoeRepository()
    book = repo.load(profile)
    shoe = book.get(shoe_id)

    if shoe is None:

        raise HTTPException(status_code=404, detail="Tênis não encontrado.")

    if body.name is not None and body.name.strip():

        shoe.name = body.name.strip()

    if body.nickname is not None:

        shoe.nickname = body.nickname.strip() or None

    if body.category is not None:

        shoe.category = canonical_category(body.category) or (
            body.category.strip() or None
        )

    if body.alert_threshold_km is not None and body.alert_threshold_km > 0:

        shoe.alert_threshold_km = float(body.alert_threshold_km)
        shoe.wear_alerted = shoe.total_km >= shoe.alert_threshold_km

    if body.total_km is not None:

        ShoeCommandEngine._set_km(book, shoe.id, body.total_km)

    if body.retired is not None:

        shoe.retired = bool(body.retired)

        # aposentou o par que era o do dia a dia? o default fica órfão —
        # promove o par ativo de maior rodagem, se houver.
        if shoe.retired and shoe.is_default:

            shoe.is_default = False

            rest = book.active()

            if rest:

                ShoeCommandEngine._make_default(
                    book, max(rest, key=lambda s: s.total_km)
                )

    if body.is_default is True and not shoe.retired:

        ShoeCommandEngine._make_default(book, shoe)

    elif body.is_default is False:

        shoe.is_default = False

    repo.save(profile, book)

    return _shoe_dict(shoe)


@router.delete("/{shoe_id}")
async def delete_shoe(shoe_id: str, profile: str = Depends(current_profile)):
    """Remove um par do armário de vez (para um cadastro errado). Pra guardar o
    histórico, prefira aposentar (PATCH retired=true)."""

    repo = ShoeRepository()
    book = repo.load(profile)
    shoe = book.get(shoe_id)

    if shoe is None:

        raise HTTPException(status_code=404, detail="Tênis não encontrado.")

    was_default = shoe.is_default

    book.shoes = [s for s in book.shoes if s.id != shoe_id]
    book.rules = [r for r in book.rules if r.shoe_id != shoe_id]

    # se removeu o do dia a dia, promove outro ativo
    if was_default:

        rest = book.active()

        if rest:

            ShoeCommandEngine._make_default(
                book, max(rest, key=lambda s: s.total_km)
            )

    repo.save(profile, book)

    return {"ok": True}
