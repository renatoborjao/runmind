"""Distribuição do treino nas zonas de FC + carga de Edwards.

Edwards TRIMP (1993): divide o tempo em 5 zonas de FC e pesa cada uma
1..5 — carga = Σ (minutos na zona_i × i). Captura a DISTRIBUIÇÃO do esforço que
a FC média achata: um tiro (muito tempo em Z5) pesa muito mais que uma rodagem
de mesma FC média. Puro/testável. Ver [[project_analise_corpo_garmin]]."""

# peso de cada zona Z1..Z5. As zonas em si vêm da régua única do atleta
# ([[HrZoneResolver]] — relógio, reserva de FC ou %FCmáx).
_ZONE_WEIGHTS = (1, 2, 3, 4, 5)


class HrZoneCalculator:

    @staticmethod
    def edwards_load(zone_minutes: list[float] | None) -> float | None:
        """Carga de Edwards = Σ (minutos na zona × peso). None sem zonas."""

        if not zone_minutes or len(zone_minutes) != 5:

            return None

        return round(
            sum(m * w for m, w in zip(zone_minutes, _ZONE_WEIGHTS)),
            1,
        )
