"""Busca uma atividade do Garmin e a converte no mesmo `Activity` que o
pipeline de análise já consome (raw imitando o formato Strava: splits_metric,
_streams, laps). O diferencial: os `typed_splits` do Garmin — as voltas já
ROTULADAS (aquecimento/tiro/recuperação) do treino estruturado — viram a
IntervalAnalysis EXATA, sem o detector fuzzy que erra.

NOTA: os nomes de campo do Garmin são lidos de forma defensiva (vários
fallbacks). Confirmar com uma atividade real via garmin_dump.py."""

from datetime import datetime, timezone

from app.domain.entities.activity import Activity
from app.domain.entities.interval_analysis import IntervalAnalysis
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)

# tipos de volta do Garmin que são ESFORÇO (tiro) vs RECUPERAÇÃO
_EFFORT_TYPES = {"INTERVAL", "ACTIVE"}
_RECOVERY_TYPES = {"RECOVERY", "REST"}


def _first(d: dict, *keys, default=None):
    """Primeiro valor não-nulo entre as chaves (o Garmin varia o nome/local)."""

    for key in keys:

        value = d.get(key)

        if value is not None:

            return value

    return default


def _speed_to_pace(speed_ms: float | None) -> float | None:
    """m/s -> min/km (o formato que o resto do sistema usa)."""

    if not speed_ms or speed_ms <= 0:

        return None

    return round((1000 / speed_ms) / 60, 3)


class GarminActivitySource:

    @staticmethod
    def fetch(profile: str, activity_id: int) -> Activity:
        """Monta o Activity a partir dos dados do Garmin. Pipeline de
        análise roda igual — só a FONTE muda."""

        garmin = GarminClient.connect(profile)

        summary = garmin.get_activity(activity_id)

        raw: dict = dict(summary)

        # ---- streams (série segundo-a-segundo) p/ o pipeline atual ----
        try:

            details = garmin.get_activity_details(activity_id)

            raw["_streams"] = GarminActivitySource._streams(details)

        except Exception as e:

            print(f"Garmin: streams indisponíveis p/ {activity_id}: {e}")

            raw["_streams"] = {}

        # ---- splits por km (ficha/parciais) ----
        try:

            splits = garmin.get_activity_splits(activity_id)

            raw["splits_metric"] = GarminActivitySource._km_splits(splits)

        except Exception as e:

            print(f"Garmin: splits indisponíveis p/ {activity_id}: {e}")

        # ---- typed splits: os tiros EXATOS (rotulados) ----
        try:

            typed = garmin.get_activity_typed_splits(activity_id)

            interval = GarminActivitySource._exact_interval(typed)

            if interval is not None:

                raw["_garmin_interval"] = interval

        except Exception as e:

            print(f"Garmin: typed_splits indisponíveis p/ {activity_id}: {e}")

        return GarminActivitySource._to_activity(activity_id, summary, raw)

    # ------------------------------------------------------------------

    @staticmethod
    def _to_activity(activity_id: int, s: dict, raw: dict) -> Activity:

        activity_type = s.get("activityType") or {}

        type_key = (
            activity_type.get("typeKey")
            if isinstance(activity_type, dict)
            else str(activity_type)
        ) or "running"

        start = _first(s, "startTimeGMT", "startTimeLocal")

        # esteira: análise trata distância/pace como estimados
        raw["trainer"] = bool(
            _first(s, "isIndoor", default=False)
            or "treadmill" in type_key.lower()
        )

        return Activity(
            id=activity_id,
            name=_first(s, "activityName", default="Corrida"),
            sport=GarminActivitySource._sport(type_key),
            start_date=GarminActivitySource._parse_date(start),
            timezone=_first(s, "timeZoneId", default="UTC"),
            distance=float(_first(s, "distance", default=0) or 0),
            moving_time=int(_first(s, "movingDuration", "duration", default=0) or 0),
            elapsed_time=int(_first(s, "duration", "elapsedDuration", default=0) or 0),
            average_speed=float(_first(s, "averageSpeed", default=0) or 0),
            max_speed=float(_first(s, "maxSpeed", default=0) or 0),
            average_heartrate=_num(_first(s, "averageHR", "averageHeartRate")),
            max_heartrate=_num(_first(s, "maxHR", "maxHeartRate")),
            elevation_gain=float(_first(s, "elevationGain", default=0) or 0),
            elevation_high=_num(_first(s, "maxElevation")),
            elevation_low=_num(_first(s, "minElevation")),
            start_latitude=_num(_first(s, "startLatitude")),
            start_longitude=_num(_first(s, "startLongitude")),
            end_latitude=_num(_first(s, "endLatitude")),
            end_longitude=_num(_first(s, "endLongitude")),
            kudos=0,
            comments=0,
            suffer_score=None,
            raw=raw,
        )

    @staticmethod
    def _sport(type_key: str) -> str:
        """Mapeia o tipo Garmin pro vocabulário do sistema (FOOT_SPORTS)."""

        key = type_key.lower()

        if "walk" in key:

            return "Walk"

        if "hik" in key:

            return "Hike"

        if "trail" in key:

            return "TrailRun"

        # running, treadmill_running, indoor_running, track_running...
        return "Run"

    @staticmethod
    def _parse_date(value) -> datetime:

        if not value:

            return datetime.now(timezone.utc)

        text = str(value).replace("Z", "").replace("T", " ").strip()

        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):

            try:

                dt = datetime.strptime(text, fmt)

                return dt.replace(tzinfo=timezone.utc)

            except ValueError:

                continue

        return datetime.now(timezone.utc)

    @staticmethod
    def _streams(details: dict) -> dict:
        """Converte os métricas detalhadas do Garmin (arrays paralelos)
        no formato de stream do Strava (velocity_smooth/heartrate/distance/
        cadence). O Garmin traz metricDescriptors + activityDetailMetrics."""

        descriptors = details.get("metricDescriptors") or []

        rows = details.get("activityDetailMetrics") or []

        # mapa: chave Garmin -> nossa chave de stream
        wanted = {
            "directSpeed": "velocity_smooth",
            "directHeartRate": "heartrate",
            "sumDistance": "distance",
            "directRunCadence": "cadence",
            "directDoubleCadence": "cadence",
        }

        index: dict[int, str] = {}

        for desc in descriptors:

            key = desc.get("key") or desc.get("metricsKey")

            if key in wanted:

                index[desc.get("metricsIndex")] = wanted[key]

        streams: dict[str, list] = {v: [] for v in wanted.values()}

        for row in rows:

            metrics = row.get("metrics") or []

            for idx, target in index.items():

                if idx is not None and idx < len(metrics):

                    streams[target].append(metrics[idx])

        # remove streams vazios
        return {k: v for k, v in streams.items() if v}

    @staticmethod
    def _km_splits(splits: dict) -> list[dict]:
        """Voltas por km do Garmin -> formato splits_metric do Strava
        ({distance, average_speed, average_heartrate})."""

        items = (
            splits.get("lapDTOs")
            or splits.get("splits")
            or (splits if isinstance(splits, list) else [])
        )

        result = []

        for it in items:

            result.append(
                {
                    "distance": _first(it, "distance", default=0),
                    "average_speed": _first(it, "averageSpeed", default=0),
                    "average_heartrate": _first(
                        it, "averageHR", "averageHeartRate"
                    ),
                }
            )

        return result

    @staticmethod
    def _exact_interval(typed: dict) -> IntervalAnalysis | None:
        """O PULO DO GATO: monta a IntervalAnalysis a partir das voltas já
        ROTULADAS pelo Garmin (esforço vs recuperação) — reps exatos,
        alinhados ao treino proposto, sem inferência."""

        splits = (
            typed.get("splits")
            or typed.get("lapDTOs")
            or (typed if isinstance(typed, list) else [])
        )

        efforts = []

        recovery_hrs = []

        for sp in splits:

            sp_type = str(
                _first(sp, "type", "splitType", default="")
            ).upper()

            avg_speed = _first(sp, "averageSpeed", default=0)

            hr = _num(_first(sp, "averageHR", "averageHeartRate"))

            max_hr = _num(_first(sp, "maxHR", "maxHeartRate")) or hr

            if sp_type in _EFFORT_TYPES:

                efforts.append(
                    {
                        "distance_m": round(
                            float(_first(sp, "distance", default=0) or 0)
                        ),
                        "pace": _speed_to_pace(avg_speed),
                        "peak_hr": int(max_hr) if max_hr else None,
                    }
                )

            elif sp_type in _RECOVERY_TYPES and hr:

                recovery_hrs.append(hr)

        if len(efforts) < 2:

            return None

        paces = [e["pace"] for e in efforts if e["pace"]]

        peaks = [e["peak_hr"] for e in efforts if e["peak_hr"]]

        return IntervalAnalysis(
            rep_count=len(efforts),
            avg_rep_pace=round(sum(paces) / len(paces), 3) if paces else 0,
            avg_peak_hr=round(sum(peaks) / len(peaks)) if peaks else None,
            avg_recovery_hr=(
                round(sum(recovery_hrs) / len(recovery_hrs))
                if recovery_hrs
                else None
            ),
            reps=efforts,
        )


def _num(value) -> float | None:

    return float(value) if isinstance(value, (int, float)) else None
