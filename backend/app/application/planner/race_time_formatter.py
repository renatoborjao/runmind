class RaceTimeFormatter:

    @staticmethod
    def format(seconds: float) -> str:
        """Segundos -> "H:MM:SS" (ou "M:SS" se menos de 1h)."""

        total = round(seconds)

        hours, remainder = divmod(total, 3600)

        minutes, secs = divmod(remainder, 60)

        if hours:

            return f"{hours}:{minutes:02d}:{secs:02d}"

        return f"{minutes}:{secs:02d}"

    @staticmethod
    def parse_hms(target_time: str | None) -> int | None:
        """"HH:MM:SS" -> segundos. Formato inválido/ausente -> None (nunca
        levanta — o campo vem de texto livre do onboarding)."""

        if not target_time:

            return None

        parts = target_time.strip().split(":")

        if len(parts) != 3:

            return None

        try:

            hours, minutes, seconds = (int(p) for p in parts)

        except ValueError:

            return None

        return hours * 3600 + minutes * 60 + seconds
