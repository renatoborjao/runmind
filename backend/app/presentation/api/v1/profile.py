from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/profile", tags=["Profile"])

_DAY_PT = {
    "Monday": "Seg", "Tuesday": "Ter", "Wednesday": "Qua", "Thursday": "Qui",
    "Friday": "Sex", "Saturday": "Sáb", "Sunday": "Dom",
}


def _serialize(r) -> dict:

    parts = (r.name or "").strip().split(" ", 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""

    return {
        "id": r.id,
        "first_name": first,
        "last_name": last,
        "name": r.name,
        "email": r.email,
        "age": r.age,
        "weight": r.weight,
        "height": r.height,
        "sex": r.sex,
        "avatar": r.avatar,
        "timezone": r.timezone,
        "goal": r.goal,
        "weekly_training_days": r.weekly_training_days,
        "preferred_running_days": [
            _DAY_PT.get(d, d) for d in (r.preferred_running_days or [])
        ],
        "target_race": r.target_race,
        "race_date": r.race_date,
        "target_time": r.target_time,
    }


@router.get("")
async def get_profile(profile: str = Depends(current_profile)):
    """Dados do perfil do atleta logado."""

    try:

        r = RunnerProfileRepository().load(profile)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    return _serialize(r)


class ProfilePatch(BaseModel):
    """Só dados PESSOAIS/de corpo. Meta, dias de treino e prova NÃO entram aqui
    de propósito: são dinâmicos (memória evolutiva/plano) e mudam pelo coach —
    sobrescrever campo cru desalinharia o plano. Ver [[feedback_tudo_dinamico]]."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    age: int | None = None
    weight: float | None = None
    height: float | None = None
    sex: str | None = None
    avatar: str | None = None   # data URL de imagem, ou "" pra remover


@router.patch("")
async def update_profile(
    body: ProfilePatch, profile: str = Depends(current_profile)
):
    """Edita os dados pessoais do atleta (nome, e-mail, idade, peso, altura,
    sexo). Merge — só toca no que veio."""

    repo = RunnerProfileRepository()

    try:

        r = repo.load(profile)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    updates: dict = {}

    # nome: recompõe "nome sobrenome" preservando a parte não enviada
    if body.first_name is not None or body.last_name is not None:

        parts = (r.name or "").strip().split(" ", 1)
        cur_first = parts[0] if parts else ""
        cur_last = parts[1] if len(parts) > 1 else ""

        first = (body.first_name if body.first_name is not None else cur_first).strip()
        last = (body.last_name if body.last_name is not None else cur_last).strip()

        name = f"{first} {last}".strip()

        if not name:

            raise HTTPException(status_code=422, detail="O nome não pode ficar vazio.")

        updates["name"] = name

    if body.email is not None:

        email = body.email.strip()

        if email:

            if "@" not in email or "." not in email:

                raise HTTPException(status_code=422, detail="E-mail inválido.")

            owner = repo.find_by_email(email)  # chave do perfil dono, ou None

            if owner is not None and owner != profile:

                raise HTTPException(
                    status_code=409, detail="Esse e-mail já está em uso por outra conta."
                )

            updates["email"] = email

        else:

            updates["email"] = None

    if body.age is not None:

        if not (5 <= body.age <= 120):

            raise HTTPException(status_code=422, detail="Idade fora do intervalo.")

        updates["age"] = int(body.age)

    if body.weight is not None:

        if not (20 <= body.weight <= 300):

            raise HTTPException(status_code=422, detail="Peso fora do intervalo (kg).")

        updates["weight"] = round(float(body.weight), 1)

    if body.height is not None:

        if not (1.0 <= body.height <= 2.5):

            raise HTTPException(status_code=422, detail="Altura em metros (ex.: 1,75).")

        updates["height"] = round(float(body.height), 2)

    if body.sex is not None:

        s = body.sex.strip().upper()

        if s in ("", "-"):

            updates["sex"] = None

        elif s in ("M", "F"):

            updates["sex"] = s

        else:

            raise HTTPException(status_code=422, detail="Sexo deve ser M ou F.")

    if body.avatar is not None:

        av = body.avatar.strip()

        if not av:

            updates["avatar"] = None

        elif not av.startswith("data:image/"):

            raise HTTPException(status_code=422, detail="Foto inválida.")

        elif len(av) > 400_000:

            raise HTTPException(
                status_code=413, detail="Foto muito grande — tenta outra."
            )

        else:

            updates["avatar"] = av

    if updates:

        repo.update_fields(profile, updates)

    return _serialize(repo.load(profile))
