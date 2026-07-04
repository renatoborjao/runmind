from app.core.weekdays import WEEKDAYS

# índice do dia da semana (segunda=0 ... domingo=6)
_DAY_INDEX = {name.lower(): i for i, name in WEEKDAYS.items()}

# Qualidade disponível por nível (iniciante nunca faz tiro/limiar forte).
_BEGINNER_QUALITY = ["PROGRESSION", "FARTLEK"]

# Qualidade por fase (intermediário/avançado): base é leve, build/pico
# específico, taper afia curto.
_QUALITY_BY_PHASE = {
    "BASE": ["TEMPO", "FARTLEK"],
    "BUILD": ["VO2", "TEMPO"],
    "PEAK": ["VO2", "TEMPO"],
    "TAPER": ["FARTLEK", "TEMPO"],
}


class SessionComposer:
    """Decide os TIPOS de treino da semana (do toolbox de 7) conforme
    nível + fase + nº de dias, e os distribui pelos dias do atleta com
    regras simples: longão no fim de semana, qualidade espaçada, e
    regenerativo quando há muitos dias. Não decide distância/pace — isso
    é do distribuidor/gerador."""

    @staticmethod
    def compose(
        level: str,
        phase: str,
        running_days: list[str],
    ) -> list[dict]:

        days_sorted = sorted(
            running_days,
            key=lambda day: _DAY_INDEX.get(day.lower(), 0),
        )

        n = len(days_sorted)

        if n == 0:

            return []

        if n == 1:

            return [{"day": days_sorted[0], "type": "EASY"}]

        # longão sempre no último dia (tende ao fim de semana, já ordenado)
        long_day = days_sorted[-1]

        available = days_sorted[:-1]

        quality_types = SessionComposer._quality_types(level, phase)

        quality_count = SessionComposer._quality_count(level, n)

        quality_days = SessionComposer._pick_quality_days(
            available,
            long_day,
            quality_count,
        )

        assignment: dict[str, str] = {long_day: "LONG_RUN"}

        for i, day in enumerate(quality_days):

            assignment[day] = quality_types[i % len(quality_types)]

        # dias restantes: regenerativo no primeiro (pós-fim de semana),
        # o resto rodagem leve
        rest = [day for day in available if day not in quality_days]

        for position, day in enumerate(rest):

            first_and_crowded = position == 0 and n >= 6

            assignment[day] = "RECOVERY" if first_and_crowded else "EASY"

        return [
            {"day": day, "type": assignment[day]}
            for day in days_sorted
        ]

    @staticmethod
    def _quality_types(level: str, phase: str) -> list[str]:

        if level == "Beginner":

            return _BEGINNER_QUALITY

        return _QUALITY_BY_PHASE.get(phase, ["TEMPO", "VO2"])

    @staticmethod
    def _quality_count(level: str, n_days: int) -> int:
        """Quantas sessões de qualidade na semana."""

        if n_days < 3:

            return 0

        if level == "Beginner":

            return 1

        if n_days >= 5:

            return 2

        return 1

    @staticmethod
    def _pick_quality_days(
        available: list[str],
        long_day: str,
        count: int,
    ) -> list[str]:
        """Escolhe dias de qualidade evitando dias de calendário
        consecutivos entre si e coladas no longão. Relaxa a regra se os
        dias escolhidos pelo atleta forem todos grudados."""

        if count <= 0:

            return []

        picked: list[str] = []

        for strict in (True, False):

            picked = []

            for day in available:

                if len(picked) >= count:

                    break

                if strict and SessionComposer._adjacent(
                    day,
                    picked + [long_day],
                ):

                    continue

                picked.append(day)

            if len(picked) >= count:

                break

        return picked[:count]

    @staticmethod
    def _adjacent(day: str, others: list[str]) -> bool:
        """Dia de calendário colado (diferença de 1) a algum dos outros."""

        index = _DAY_INDEX.get(day.lower(), 0)

        return any(
            abs(index - _DAY_INDEX.get(other.lower(), 0)) == 1
            for other in others
        )
