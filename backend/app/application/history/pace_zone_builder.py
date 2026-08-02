from app.domain.entities.pace_model import PaceModel
from app.domain.entities.pace_zones import PaceZone, PaceZones

# o quão mais lento que o "fácil máx" vai o regenerativo (Z1)
_RECOVERY_SLACK = 0.45


class PaceZoneBuilder:
    """Traduz o PaceModel (fonte única, ancorada no VDOT real) nas 5 zonas de
    treino Z1..Z5. As zonas SÃO as faixas E/M/T/I/R do modelo — não um segundo
    cálculo solto —, então batem com o que o plano prescreve e sobem sozinhas
    conforme o atleta evolui. Ver [[PaceModelBuilder]]."""

    @staticmethod
    def build(model: PaceModel) -> PaceZones:

        zones = [
            PaceZone(
                number=1,
                name="Recuperação",
                purpose="trote regenerativo, bem leve — solta as pernas",
                fast=model.easy_max,
                slow=round(model.easy_max + _RECOVERY_SLACK, 2),
            ),
            PaceZone(
                number=2,
                name="Fácil / Base",
                purpose="o pão-com-manteiga: dá pra conversar, constrói a base",
                fast=model.easy_min,
                slow=model.easy_max,
            ),
            PaceZone(
                number=3,
                name="Moderado",
                purpose="rodagem forte, ritmo de prova longa",
                fast=model.marathon,
                slow=model.easy_min,
            ),
            PaceZone(
                number=4,
                name="Limiar",
                purpose='"confortavelmente difícil", tempo run / limiar',
                fast=model.threshold,
                slow=model.marathon,
            ),
            PaceZone(
                number=5,
                name="VO₂ / Intervalado",
                purpose="tiros de 3–5 min fortes, respiração no talo",
                fast=model.interval,
                slow=model.threshold,
            ),
        ]

        return PaceZones(zones=zones)
