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
