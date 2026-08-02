"""Cartão das zonas de pace do atleta — resposta canônica ao "quais minhas
zonas de pace?". Determinístico, sem IA. As zonas vêm do ritmo real dele, então
o cartão sempre reflete o momento atual e sobe sozinho conforme ele evolui."""

from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.pace_zones import PaceZones

_EMOJI = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}


class PaceZonesWriter:

    @staticmethod
    def write(
        zones: PaceZones,
        runner_name: str,
        estimated: bool = False,
    ) -> str:

        subtitle = (
            "Ainda são uma ESTIMATIVA (você tem pouca corrida registrada) — "
            "conforme você correr, elas se ajustam ao seu ritmo real."
            if estimated
            else "Calibradas pelo seu melhor esforço real — elas sobem "
            "sozinhas conforme você evolui."
        )

        lines = [
            f"🎯 Suas zonas de pace, {runner_name}",
            subtitle,
            "",
        ]

        # Z1..Z5, do mais leve pro mais forte (o mesmo sentido do medidor)
        for zone in zones.zones:

            band = (
                f"{PaceFormatter.format(zone.fast)}–"
                f"{PaceFormatter.format(zone.slow)}/km"
            )

            emoji = _EMOJI.get(zone.number, "•")

            lines.append(f"{emoji} Z{zone.number} · {zone.name} — {band}")

            lines.append(f"   {zone.purpose}")

        lines.append("")

        lines.append(
            "A maior parte do seu volume mora na Z2 — é ela que constrói. "
            "As zonas fortes (Z4/Z5) são tempero, em dose certa. 👊"
        )

        return "\n".join(lines)
