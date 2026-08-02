from app.application.coach.writer.pace_zones_writer import PaceZonesWriter
from app.domain.entities.pace_zones import PaceZone, PaceZones


def _zones() -> PaceZones:

    return PaceZones(
        zones=[
            PaceZone(1, "Recuperação", "leve", 6.35, 6.80),
            PaceZone(2, "Fácil / Base", "base", 5.75, 6.35),
            PaceZone(3, "Moderado", "rodagem forte", 5.50, 5.75),
            PaceZone(4, "Limiar", "tempo run", 5.30, 5.50),
            PaceZone(5, "VO₂ / Intervalado", "tiros", 4.80, 5.30),
        ]
    )


def test_card_names_the_runner_and_all_five_zones():

    card = PaceZonesWriter.write(_zones(), "Renato")

    assert "Renato" in card

    for n in (1, 2, 3, 4, 5):

        assert f"Z{n}" in card


def test_card_formats_pace_band_as_min_per_km():
    """5.75 -> 5:45 e 6.35 -> 6:21 na faixa da Z2."""

    card = PaceZonesWriter.write(_zones(), "Renato")

    assert "5:45–6:21/km" in card


def test_card_includes_purpose_of_each_zone():

    card = PaceZonesWriter.write(_zones(), "Renato")

    assert "rodagem forte" in card
    assert "tempo run" in card
