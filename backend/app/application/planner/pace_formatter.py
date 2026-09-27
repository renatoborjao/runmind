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
    def for_activity(
        distance_m: float | None,
        moving_time_s: float | None,
        average_speed: float | None = None,
    ) -> str | None:
        """Ritmo médio de uma atividade, na MESMA regra do Strava/Garmin Connect:
        vem da velocidade média oficial do relógio (não de distância ÷ tempo —
        Garmin e Strava contam o tempo em movimento diferente e a cópia Garmin
        dava 6:14 onde os dois apps mostram 6:15) e ARREDONDA pro segundo
        inteiro. distância ÷ tempo só quando não há velocidade."""

        if average_speed and average_speed > 0:

            sec_per_km = 1000 / average_speed

        elif distance_m and distance_m > 0 and moving_time_s:

            sec_per_km = moving_time_s / (distance_m / 1000)

        else:

            return None

        # round no total primeiro + divmod: nunca "5:60"
        m, s = divmod(round(sec_per_km), 60)

        return f"{m}:{s:02d}"

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
