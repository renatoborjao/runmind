class PaceFormatter:

    @staticmethod
    def format(
        pace_min_km: float,
    ) -> str:

        minutes = int(pace_min_km)

        seconds = round((pace_min_km - minutes) * 60)

        if seconds == 60:

            minutes += 1

            seconds = 0

        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def to_minutes(pace: str | None) -> float | None:
        """"6:50" -> 6.833 min/km. Inverso do format. None se vier vazio/torto
        (o chamador decide o fallback)."""

        if not pace:

            return None

        try:

            minutes, seconds = pace.strip().split(":")

            return int(minutes) + int(seconds) / 60

        except (ValueError, AttributeError):

            return None
