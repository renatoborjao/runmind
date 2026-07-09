from app.application.history.interval_analyzer import IntervalAnalyzer
from app.domain.entities.activity import Activity
from app.domain.entities.workout_structure import WorkoutStructure

# Volta abaixo disso é auto-split de GPS/ruído, não um bloco planejado.
MIN_LAP_METERS = 300

# Split abaixo disso é o pedaço PARCIAL final (o "km" incompleto do fim,
# muitas vezes caminhando) — não é uma parcial de verdade, distorce tudo.
MIN_SPLIT_METERS = 600

# Variação de pace a partir da qual o treino tem "picos" (tiro vs pausa).
INTERVAL_SPREAD_LAPS = 0.25
INTERVAL_SPREAD_KM = 0.20

# Diferença entre metades pra chamar de negative/positive split.
SPLIT_TREND_MARGIN = 0.03

# Acima disto a desaceleração é ACENTUADA (quebra de verdade). Entre a
# margem e isto é só a segunda metade mais lenta — variação normal
# (subida, calor, farol), não "quebrou" (reclamação real do Renato:
# diferença pequena no fim virou "quebrou" na análise da IA).
SPLIT_FADE_STRONG = 0.10


class WorkoutStructureBuilder:
    """Extrai a estrutura interna do treino do `raw` do Strava. Só leitura
    do que já veio — não busca nada novo."""

    @staticmethod
    def build(
        activity: Activity,
    ) -> WorkoutStructure:

        raw = activity.raw or {}

        # descarta o pedaço parcial final (km incompleto, muitas vezes
        # caminhando) que joga um "32:00 min/km" na ficha
        km_records = WorkoutStructureBuilder._km_records(
            [
                split
                for split in (raw.get("splits_metric") or [])
                if (split.get("distance") or 0) >= MIN_SPLIT_METERS
            ]
        )

        km_splits = [record["pace"] for record in km_records]

        km_hr = [record["hr"] for record in km_records]

        # tiros pelo stream (fonte de verdade pra intervalado curto)
        streams = raw.get("_streams") or {}

        interval = IntervalAnalyzer.analyze(
            streams.get("velocity_smooth") or [],
            streams.get("heartrate") or [],
            streams.get("distance") or [],
        )

        lap_paces = WorkoutStructureBuilder._paces(
            [
                lap
                for lap in (raw.get("laps") or [])
                if (lap.get("distance") or 0) >= MIN_LAP_METERS
            ]
        )

        fastest = min(km_splits) if km_splits else None
        slowest = max(km_splits) if km_splits else None

        pace_spread = (
            (slowest - fastest) / fastest
            if fastest
            else None
        )

        return WorkoutStructure(
            km_splits=km_splits,
            km_hr=km_hr,
            lap_count=len(lap_paces),
            lap_paces=lap_paces,
            fastest_km_pace=fastest,
            slowest_km_pace=slowest,
            pace_spread=(
                round(pace_spread, 3)
                if pace_spread is not None
                else None
            ),
            split_trend=WorkoutStructureBuilder._trend(km_splits),
            is_interval=(
                interval is not None
                or WorkoutStructureBuilder._is_interval(
                    km_splits,
                    lap_paces,
                )
            ),
            interval=interval,
            cadence_spm=WorkoutStructureBuilder._cadence(raw),
            hr_avg=WorkoutStructureBuilder._int(
                raw.get("average_heartrate")
            ),
            hr_max=WorkoutStructureBuilder._int(
                raw.get("max_heartrate")
            ),
            has_detail=bool(km_splits or lap_paces),
        )

    @staticmethod
    def _paces(
        segments: list[dict],
    ) -> list[float]:
        """Pace (min/km) de cada segmento, ignorando os parados/sem
        velocidade (evita divisão por zero em pausa de caminhada)."""

        return [
            record["pace"]
            for record in WorkoutStructureBuilder._km_records(segments)
        ]

    @staticmethod
    def _km_records(
        segments: list[dict],
    ) -> list[dict]:
        """Pace (min/km) + FC média de cada segmento, ignorando os
        parados/sem velocidade (evita divisão por zero em pausa)."""

        records = []

        for segment in segments:

            speed = segment.get("average_speed") or 0

            if speed <= 0:

                continue

            records.append(
                {
                    "pace": round((1000 / speed) / 60, 2),
                    "hr": WorkoutStructureBuilder._int(
                        segment.get("average_heartrate")
                    ),
                }
            )

        return records

    @staticmethod
    def _trend(
        km_splits: list[float],
    ) -> str:

        if len(km_splits) < 2:

            return "unknown"

        half = len(km_splits) // 2

        first = sum(km_splits[:half]) / half

        second = sum(km_splits[half:]) / (len(km_splits) - half)

        # pace menor = mais rápido
        if second < first * (1 - SPLIT_TREND_MARGIN):

            return "negative"

        # queda forte de ritmo é uma coisa; segunda metade um pouco mais
        # lenta é outra — misturar as duas fazia a análise chamar
        # variação normal de "quebra"
        if second > first * (1 + SPLIT_FADE_STRONG):

            return "positive"

        if second > first * (1 + SPLIT_TREND_MARGIN):

            return "positive_mild"

        return "even"

    @staticmethod
    def _is_interval(
        km_splits: list[float],
        lap_paces: list[float],
    ) -> bool:
        """Tiros alternados: preferimos as voltas manuais (sinal forte de
        treino estruturado); sem elas, caímos na variação entre kms."""

        if len(lap_paces) >= 4:

            spread = (max(lap_paces) - min(lap_paces)) / min(lap_paces)

            if spread >= INTERVAL_SPREAD_LAPS:

                return True

        if len(km_splits) >= 4:

            spread = (max(km_splits) - min(km_splits)) / min(km_splits)

            if spread >= INTERVAL_SPREAD_KM:

                return True

        return False

    @staticmethod
    def _cadence(
        raw: dict,
    ) -> int | None:
        """Cadência em passos/min. Strava reporta RPM por perna (x2). Se o
        resumo não trouxe (comum na esteira), tenta a média do stream."""

        cadence = raw.get("average_cadence")

        if not cadence:

            stream = (raw.get("_streams") or {}).get("cadence") or []

            values = [value for value in stream if value]

            if values:

                cadence = sum(values) / len(values)

        if not cadence:

            return None

        return int(round(cadence * 2))

    @staticmethod
    def _int(
        value,
    ) -> int | None:

        if value is None:

            return None

        return int(round(value))
