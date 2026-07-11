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

# O Garmin rotula as voltas do treino estruturado com sufixo: esforço =
# "INTERVAL_ACTIVE" (ou "ACTIVE"/"INTERVAL"), recuperação = "INTERVAL_RECOVERY"
# / "REST" (confirmado com atividade real). Casamos por SUBSTRING, checando
# recuperação primeiro (senão "INTERVAL_RECOVERY" cairia como esforço).
def _is_recovery_type(sp_type: str) -> bool:

    return "RECOVERY" in sp_type or "REST" in sp_type


def _is_effort_type(sp_type: str) -> bool:

    return not _is_recovery_type(sp_type) and (
        "ACTIVE" in sp_type or sp_type == "INTERVAL"
    )


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

        summary_dto = summary.get("summaryDTO") or {}

        # cadência pro pipeline atual (ficha/estrutura). O Garmin dá
        # averageRunCadence em passos/min TOTAL (~162); o builder
        # compartilhado dobra um valor por-perna (padrão Strava), então
        # passamos a METADE pra o ×2 reconstituir o total certo.
        if summary_dto.get("averageRunCadence") is not None:

            raw["average_cadence"] = summary_dto["averageRunCadence"] / 2

        # bundle RICO do que o Garmin mediu — pra análise ficar de acordo com
        # o EXECUTADO: efeito de treino, dinâmica de corrida, potência,
        # RPE/percepção, carga/recuperação, temperatura...
        raw["_garmin_metrics"] = GarminActivitySource._rich_metrics(summary_dto)

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

        # get_activity devolve DTOs aninhados: os números vivem no summaryDTO,
        # o tipo no activityTypeDTO, o fuso no timeZoneUnitDTO (confirmado com
        # atividade real, perfil renato2)
        sd = s.get("summaryDTO") or {}

        type_dto = s.get("activityTypeDTO") or {}

        tz_dto = s.get("timeZoneUnitDTO") or {}

        type_key = str(type_dto.get("typeKey") or "running")

        start = _first(sd, "startTimeGMT", "startTimeLocal")

        # esteira: análise trata distância/pace como estimados
        raw["trainer"] = bool(
            _first(sd, "isIndoor", default=False)
            or "treadmill" in type_key.lower()
            or "indoor" in type_key.lower()
        )

        return Activity(
            id=activity_id,
            name=_first(s, "activityName", default="Corrida"),
            sport=GarminActivitySource._sport(type_key),
            start_date=GarminActivitySource._parse_date(start),
            timezone=_first(tz_dto, "timeZone", "unitKey", default="UTC"),
            distance=float(_first(sd, "distance", default=0) or 0),
            moving_time=int(
                _first(sd, "movingDuration", "duration", default=0) or 0
            ),
            elapsed_time=int(
                _first(sd, "elapsedDuration", "duration", default=0) or 0
            ),
            average_speed=float(_first(sd, "averageSpeed", default=0) or 0),
            max_speed=float(_first(sd, "maxSpeed", default=0) or 0),
            average_heartrate=_num(_first(sd, "averageHR", "averageHeartRate")),
            max_heartrate=_num(_first(sd, "maxHR", "maxHeartRate")),
            elevation_gain=float(_first(sd, "elevationGain", default=0) or 0),
            elevation_high=_num(_first(sd, "maxElevation")),
            elevation_low=_num(_first(sd, "minElevation")),
            start_latitude=_num(_first(sd, "startLatitude")),
            start_longitude=_num(_first(sd, "startLongitude")),
            end_latitude=_num(_first(sd, "endLatitude")),
            end_longitude=_num(_first(sd, "endLongitude")),
            kudos=0,
            comments=0,
            suffer_score=None,
            raw=raw,
        )

    # métricas ricas do Garmin (chave nossa -> chave do summaryDTO). São o
    # "de acordo com o executado": alimentam a análise (IA + ficha).
    _RICH_FIELDS = {
        "avg_cadence": "averageRunCadence",
        "max_cadence": "maxRunCadence",
        "avg_power": "averagePower",
        "max_power": "maxPower",
        "normalized_power": "normalizedPower",
        "ground_contact_ms": "groundContactTime",
        "stride_length_cm": "strideLength",
        "vertical_oscillation_cm": "verticalOscillation",
        "vertical_ratio": "verticalRatio",
        "grade_adjusted_speed": "avgGradeAdjustedSpeed",
        "training_effect": "trainingEffect",
        "training_effect_label": "trainingEffectLabel",
        "aerobic_effect_msg": "aerobicTrainingEffectMessage",
        "anaerobic_effect": "anaerobicTrainingEffect",
        "anaerobic_effect_msg": "anaerobicTrainingEffectMessage",
        "workout_feel": "directWorkoutFeel",
        "workout_rpe": "directWorkoutRpe",
        "body_battery_delta": "differenceBodyBattery",
        "moderate_minutes": "moderateIntensityMinutes",
        "vigorous_minutes": "vigorousIntensityMinutes",
        "calories": "calories",
        "avg_temperature": "averageTemperature",
        "max_temperature": "maxTemperature",
        "min_hr": "minHR",
        "steps": "steps",
        "elevation_loss": "elevationLoss",
    }

    @staticmethod
    def _rich_metrics(summary_dto: dict) -> dict:
        """Só os campos presentes (não-nulos) entram — cada relógio/treino
        traz um subconjunto (potência e dinâmica dependem de sensor)."""

        out = {}

        for ours, garmin_key in GarminActivitySource._RICH_FIELDS.items():

            value = summary_dto.get(garmin_key)

            if value is not None:

                out[ours] = value

        return out

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

            if _is_effort_type(sp_type):

                efforts.append(
                    {
                        "distance_m": round(
                            float(_first(sp, "distance", default=0) or 0)
                        ),
                        "pace": _speed_to_pace(avg_speed),
                        "peak_hr": int(max_hr) if max_hr else None,
                    }
                )

            elif _is_recovery_type(sp_type) and hr:

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
