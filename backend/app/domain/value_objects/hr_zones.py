"""Zonas de FC do ATLETA — a régua única que gráfico, mensagem, prompt da IA e
carga usam. Antes cada parte tinha a sua (gráfico por %FCmáx de idade, texto
relativo à FC média de costume) e se contradiziam: rodagem leve do Renato
(144 bpm) saía "Z2" no texto e Z3/Z4 no gráfico, enquanto o relógio dizia Z2.

5 pisos (Z1..Z5) em bpm; abaixo do piso de Z1 não é zona (repouso/deriva).
Fontes, da mais pra menos fiel (ver [[HrZoneResolver]]):
  - "garmin": as zonas CONFIGURADAS no relógio (o que o atleta vê no app dele)
  - "hrr": reserva de FC (Karvonen) 50/60/70/80/90% — o padrão do Garmin
  - "max": %FCmáx 50/60/70/80/90 — quando falta FC de repouso."""

from __future__ import annotations

from dataclasses import dataclass

_PCTS = (0.50, 0.60, 0.70, 0.80, 0.90)


@dataclass(frozen=True, slots=True)
class HrZones:

    floors: tuple[int, int, int, int, int]

    method: str

    max_hr: int | None = None

    resting_hr: int | None = None

    @staticmethod
    def from_hrr(max_hr: int, resting_hr: int) -> "HrZones":

        reserve = max_hr - resting_hr

        return HrZones(
            floors=tuple(round(resting_hr + p * reserve) for p in _PCTS),
            method="hrr",
            max_hr=max_hr,
            resting_hr=resting_hr,
        )

    @staticmethod
    def from_max(max_hr: int) -> "HrZones":

        return HrZones(
            floors=tuple(round(p * max_hr) for p in _PCTS),
            method="max",
            max_hr=max_hr,
        )

    @staticmethod
    def from_dict(data: dict | None) -> "HrZones | None":
        """Zonas guardadas no perfil (vindas do relógio). None se inválidas."""

        if not isinstance(data, dict):

            return None

        floors = data.get("floors")

        if (
            not isinstance(floors, (list, tuple))
            or len(floors) != 5
            or not all(isinstance(f, (int, float)) and f > 0 for f in floors)
            or list(floors) != sorted(floors)
        ):

            return None

        return HrZones(
            floors=tuple(int(f) for f in floors),
            method=str(data.get("method") or "garmin"),
            max_hr=data.get("max_hr"),
            resting_hr=data.get("resting_hr"),
        )

    def to_dict(self) -> dict:

        return {
            "floors": list(self.floors),
            "method": self.method,
            "max_hr": self.max_hr,
            "resting_hr": self.resting_hr,
        }

    def zone_of(self, hr: float | None) -> int | None:
        """Zona 1..5 de uma FC; None abaixo do piso de Z1 (ou sem FC)."""

        if not hr or hr < self.floors[0]:

            return None

        zone = 1

        for i, floor in enumerate(self.floors):

            if hr >= floor:

                zone = i + 1

        return zone

    def minutes(
        self,
        heartrate: list,
        moving_time_sec: int,
    ) -> list[float] | None:
        """Minutos em cada zona [Z1..Z5] a partir do stream. Usa a FRAÇÃO de
        amostras × tempo em movimento (robusto à taxa de amostragem, que varia
        entre relógios/fontes). None sem stream utilizável."""

        if moving_time_sec <= 0:

            return None

        samples = [h for h in (heartrate or []) if h and h > 0]

        if len(samples) < 30:  # stream curto/ruído não vira distribuição

            return None

        counts = [0] * 5

        for hr in samples:

            zone = self.zone_of(hr)

            if zone is not None:

                counts[zone - 1] += 1

        minutes = moving_time_sec / 60

        return [round(c / len(samples) * minutes, 2) for c in counts]

    def describe(self) -> str:
        """Faixas legíveis pro prompt da IA: 'Z1 130-142 · Z2 143-155 ...'."""

        parts = []

        for i, floor in enumerate(self.floors):

            if i + 1 < len(self.floors):

                parts.append(f"Z{i + 1} {floor}-{self.floors[i + 1] - 1}")

            else:

                parts.append(f"Z{i + 1} {floor}+")

        return " · ".join(parts)


def dominant_zone(zone_minutes: list[float] | None) -> int | None:
    """Zona (1..5) onde o treino passou MAIS tempo; None sem distribuição."""

    if not zone_minutes or len(zone_minutes) != 5 or sum(zone_minutes) <= 0:

        return None

    return max(range(5), key=lambda i: zone_minutes[i]) + 1


def zone_share_label(zone_minutes: list[float] | None) -> str | None:
    """'Z2 71% · Z1 22% · Z3 1%' — zonas com ≥1% do tempo, da maior pra menor."""

    if not zone_minutes or len(zone_minutes) != 5:

        return None

    total = sum(zone_minutes)

    if total <= 0:

        return None

    shares = [
        (i + 1, round(m / total * 100))
        for i, m in enumerate(zone_minutes)
    ]

    shares = [s for s in shares if s[1] >= 1]

    shares.sort(key=lambda s: -s[1])

    return " · ".join(f"Z{z} {p}%" for z, p in shares)
