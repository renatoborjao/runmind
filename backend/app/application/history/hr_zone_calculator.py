"""Distribuição do treino nas zonas de FC + carga de Edwards.

Edwards TRIMP (1993): divide o tempo em 5 zonas por %FCmáx e pesa cada uma
1..5 — carga = Σ (minutos na zona_i × i). Captura a DISTRIBUIÇÃO do esforço que
a FC média achata: um tiro (muito tempo em Z5) pesa muito mais que uma rodagem
de mesma FC média. Puro/testável. Ver [[project_analise_corpo_garmin]]."""

# limites inferiores de cada zona em %FCmáx (Edwards clássico) e o peso.
# Abaixo de 50% da FCmáx é repouso/deriva — não conta.
_ZONE_FLOORS = (0.50, 0.60, 0.70, 0.80, 0.90)  # Z1..Z5
_ZONE_WEIGHTS = (1, 2, 3, 4, 5)


class HrZoneCalculator:

    @staticmethod
    def zone_minutes(
        heartrate: list,
        moving_time_sec: int,
        max_hr: int | None,
    ) -> list[float] | None:
        """Minutos em cada zona [Z1..Z5] a partir do stream de FC. Usa a FRAÇÃO
        de amostras em cada zona × tempo em movimento (robusto à taxa de
        amostragem, que varia entre relógios/fontes). None sem FC máx ou stream
        utilizável (aí a carga cai no método por FC média)."""

        if not max_hr or max_hr <= 0 or moving_time_sec <= 0:

            return None

        samples = [h for h in (heartrate or []) if h and h > 0]

        if len(samples) < 30:  # stream curto/ruído não vira distribuição

            return None

        counts = [0] * 5

        for hr in samples:

            zone = HrZoneCalculator._zone_index(hr / max_hr)

            if zone is not None:

                counts[zone] += 1

        total = len(samples)

        minutes = moving_time_sec / 60

        return [round(count / total * minutes, 2) for count in counts]

    @staticmethod
    def edwards_load(zone_minutes: list[float] | None) -> float | None:
        """Carga de Edwards = Σ (minutos na zona × peso). None sem zonas."""

        if not zone_minutes or len(zone_minutes) != 5:

            return None

        return round(
            sum(m * w for m, w in zip(zone_minutes, _ZONE_WEIGHTS)),
            1,
        )

    @staticmethod
    def _zone_index(pct_max: float) -> int | None:
        """Índice 0..4 da zona pra um %FCmáx; None abaixo de 50% (não conta)."""

        if pct_max < _ZONE_FLOORS[0]:

            return None

        zone = 0

        for i, floor in enumerate(_ZONE_FLOORS):

            if pct_max >= floor:

                zone = i

        return zone
