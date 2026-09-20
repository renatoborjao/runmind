from fastapi import APIRouter

from app.application.strength.strength_library import library

router = APIRouter(prefix="/strength", tags=["Strength"])


@router.get("/library")
async def strength_library():
    """Biblioteca de exercícios de fortalecimento para quem corre (conteúdo
    curado, estático, sem PII) — aberta, pra o app montar a tela e o coach
    montar rotinas a partir dela."""

    return library()
