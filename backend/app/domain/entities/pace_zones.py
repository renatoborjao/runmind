from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class PaceZone:
    """Uma zona de treino por RITMO (pace). Os limites são em min/km:
    `fast` é o ritmo mais RÁPIDO da faixa (número menor) e `slow` o mais
    lento (número maior). Ex.: Z2 fácil de 6:05 a 6:45 -> fast=6.08, slow=6.75."""

    number: int      # 1..5 (Z1 mais leve -> Z5 mais forte)
    name: str        # "Recuperação", "Fácil / Base", ...
    purpose: str     # frase curta do "pra quê" desta zona
    fast: float      # min/km — limite rápido (menor número)
    slow: float      # min/km — limite lento (maior número)


@dataclass(slots=True, frozen=True)
class PaceZones:
    """As 5 zonas de pace do atleta, calibradas pelo ritmo real dele. Sempre
    Z1..Z5 em ordem crescente de intensidade."""

    zones: list[PaceZone]
