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
    def histogram(
        heartrate: list,
        moving_time_sec: int,
    ) -> dict[str, float] | None:
        """Histograma BRUTO de FC do treino: minutos por bpm (fração de amostras
        × tempo em movimento). Não depende de régua nenhuma — as zonas saem
        dele com a régua que for a atual no momento do cálculo (a carga precisa
        de UMA régua pra janela inteira; ver [[project_carga_regua_mista]]).
        None sem stream utilizável (mesmo critério dos minutos por zona)."""

        if not moving_time_sec or moving_time_sec <= 0:

            return None

        samples = [round(h) for h in (heartrate or []) if h and 30 <= h <= 230]

        if len(samples) < 30:

            return None

        counts: dict[int, int] = {}

        for hr in samples:

            counts[hr] = counts.get(hr, 0) + 1

        minutes = moving_time_sec / 60

        total = len(samples)

        return {
            str(bpm): round(count / total * minutes, 3)
            for bpm, count in sorted(counts.items())
        }

    @staticmethod
    def edwards_load(zone_minutes: list[float] | None) -> float | None:
        """Carga de Edwards = Σ (minutos na zona × peso). None sem zonas."""

        if not zone_minutes or len(zone_minutes) != 5:

            return None

        return round(
            sum(m * w for m, w in zip(zone_minutes, _ZONE_WEIGHTS)),
            1,
        )
