from dataclasses import dataclass

# proveniência do modelo — de onde os ritmos foram ancorados
SOURCE_VDOT = "vdot"                  # VDOT do melhor esforço real (o caminho bom)
SOURCE_GARMIN = "garmin_threshold"    # limiar medido pelo relógio (premium)
SOURCE_DECLARED = "declared"          # pace autodeclarado no onboarding
SOURCE_ROOKIE = "rookie"              # sem nada — defaults conservadores


@dataclass(slots=True, frozen=True)
class PaceModel:
    """A FONTE ÚNICA de ritmos do atleta — ancorada no que ele DEMONSTROU
    (VDOT do melhor esforço real), não em offset chutado. Alimenta o plano E as
    zonas, sobe sozinha conforme ele evolui. Todos em min/km; `easy_min` é a
    ponta rápida (número menor), `easy_max` a lenta. Ver [[VdotCalculator]]."""

    easy_min: float       # ponta RÁPIDA do fácil
    easy_max: float       # ponta LENTA do fácil
    marathon: float       # ritmo de prova longa
    threshold: float      # limiar ("confortavelmente difícil")
    interval: float       # intervalado / VO2máx
    rep: float            # repetição (tiros curtos, economia)

    vdot: float | None = None    # None quando não houve esforço real (fallback)
    source: str = SOURCE_ROOKIE

    # a TRAVA DE CONDIÇÃO segurou o fácil: o VDOT sugeriu um ritmo mais rápido
    # do que o atleta REALMENTE roda de leve, então respeitamos a realidade
    # dele (nunca mandar um pace que ele não sustenta). Ver a regra do Renato.
    easy_capped: bool = False
