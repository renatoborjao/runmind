"""Busca uma atividade do Garmin e a converte no mesmo `Activity` que o
pipeline de análise já consome (raw imitando o formato Strava: splits_metric,
_streams, laps). O diferencial: os `typed_splits` do Garmin — as voltas já
ROTULADAS (aquecimento/tiro/recuperação) do treino estruturado — viram a
IntervalAnalysis EXATA, sem o detector fuzzy que erra.

NOTA: os nomes de campo do Garmin são lidos de forma defensiva (vários
fallbacks). Confirmar com uma atividade real via garmin_dump.py."""

import statistics
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


# Gate anti-falso-positivo: o Garmin rotula run-walk / rodagem com pausas
# como INTERVAL_ACTIVE/REST porcamente. Só é intervalado DE VERDADE se houver
# CONTRASTE esforço x recuperação -- resposta de FC ou esforço bem mais rápido.
_MIN_HR_SWING = 12          # bpm de queda da FC na recuperação
_MIN_SPEED_RATIO = 1.15     # esforço >=15% mais rápido que a recuperação

# Quão mais lento que a MEDIANA dos tiros um "esforço" pode ser antes de ser
# tratado como CAMINHADA (aquecimento/desaquecimento/pausa que o Garmin
# rotulou como ACTIVE). Só se aplica ao TREINADOR EXTERNO: aí as voltas são
# auto/manuais (não empurramos o treino), então o rótulo não é confiável. Nos
# NOSSOS treinos empurrados o desaquecimento vem como COOLDOWN e já é excluído
# — não mexemos nesse caminho.
_WALK_PACE_RATIO = 1.4


def _drop_walk_paced_efforts(efforts: list[dict]) -> list[dict]:
    """Tira os 'tiros' em ritmo de caminhada — bem mais lentos que a mediana
    dos esforços (era o "Tiro 9" fantasma do Mauricio: a CAM10' final que o
    Garmin rotulou INTERVAL_ACTIVE). Preserva se filtraria demais (< 2)."""

    paces = [e["pace"] for e in efforts if e["pace"]]

    if len(paces) < 2:

        return efforts

    limit = statistics.median(paces) * _WALK_PACE_RATIO

    kept = [e for e in efforts if not e["pace"] or e["pace"] <= limit]

    return kept if len(kept) >= 2 else efforts


def _real_interval(
    avg_peak_hr, avg_recovery_hr, effort_speeds, recovery_speeds
) -> bool:
    """Há contraste esforço x recuperação de treino de tiro DE VERDADE? A FC
    caiu >= _MIN_HR_SWING na recuperação, OU os esforços foram
    >= _MIN_SPEED_RATIO mais rápidos que as recuperações."""

    hr_response = (
        avg_peak_hr is not None
        and avg_recovery_hr is not None
        and avg_peak_hr - avg_recovery_hr >= _MIN_HR_SWING
    )

    pace_response = (
        bool(effort_speeds)
        and bool(recovery_speeds)
        and (sum(effort_speeds) / len(effort_speeds))
        / (sum(recovery_speeds) / len(recovery_speeds))
        >= _MIN_SPEED_RATIO
    )

    return hr_response or pace_response


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
    def fetch(
        profile: str,
        activity_id: int,
        external_coach: bool = False,
    ) -> Activity:
        """Monta o Activity a partir dos dados do Garmin. Pipeline de
        análise roda igual — só a FONTE muda.

        external_coach: as voltas do Garmin vêm de auto/manual (não
        empurramos o treino), então rótulos não confiáveis — aciona o
        filtro de tiros em ritmo de caminhada no `_exact_interval`."""

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

        # ---- parciais por km: calculadas do STREAM (distância acumulada +
        # velocidade + FC). As lapDTOs do Garmin são as VOLTAS do treino
        # (por-km só quando NÃO há estrutura); num fracionado são de
        # duração/botão e não podem virar "parciais por km" — bug do
        # Mauricio, em que só sobravam 5 laps de 1km rotulados errado. O
        # stream é a verdade real por quilômetro.
        raw["splits_metric"] = GarminActivitySource._km_splits_from_streams(
            raw.get("_streams") or {}
        )

        # ---- voltas/blocos do treino: num treino ESTRUTURADO (treinador
        # externo) as lapDTOs são os PASSOS executados (ex.: 5×3'/2'). A IA
        # compara bloco a bloco com a prescrição — não são "parciais por km".
        try:

            splits = garmin.get_activity_splits(activity_id)

            raw["_garmin_laps"] = GarminActivitySource._laps(splits)

        except Exception as e:

            print(f"Garmin: voltas indisponíveis p/ {activity_id}: {e}")

            raw["_garmin_laps"] = []

        # ---- typed splits: os tiros EXATOS (rotulados) ----
        try:

            typed = garmin.get_activity_typed_splits(activity_id)

            # TODAS as voltas classificadas (esforço/recuperação), não só os
            # tiros -- fonte pro pareamento bloco-a-bloco geral com o plano
            # (PlannedExecutionMatcher), pra QUALQUER tipo de treino.
            raw["_garmin_typed_blocks"] = GarminActivitySource._classify_splits(
                typed
            )

            interval = GarminActivitySource._exact_interval(
                typed, external_coach=external_coach
            )

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

        # HORA LOCAL de parede primeiro (o Strava também usa start_date_local):
        # startTimeGMT jogaria a corrida ~3h pra frente (07:00 BRT vira 10:00),
        # errando o dia perto da meia-noite e o casamento com a versão Strava
        # do mesmo treino. _parse_date marca +00:00, igual à convenção Strava.
        start = _first(sd, "startTimeLocal", "startTimeGMT")

        # esteira: análise trata distância/pace como estimados. GPS presente
        # (o treino tem coordenada de partida) MANDA — foi na rua, nunca é
        # esteira, mesmo que o relógio venha com isIndoor/typeKey estranho
        # (glitch de perda de GPS no meio do treino, caso real do Renato).
        has_gps = _num(_first(sd, "startLatitude")) is not None

        raw["trainer"] = bool(
            not has_gps
            and (
                _first(sd, "isIndoor", default=False)
                or "treadmill" in type_key.lower()
                or "indoor" in type_key.lower()
            )
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
        """Mapeia o tipo Garmin pro vocabulário do sistema (FOOT_SPORTS).
        Só reconhece variantes de CORRIDA como "Run" — natação/bike/força/
        etc. caem em "Other" e são filtradas por is_foot_sport() rio abaixo,
        nunca viram treino de corrida por engano (bug real: natação da
        Fernanda entrando como "Run" pelo fallback antigo, que tratava
        QUALQUER tipo não reconhecido como corrida)."""

        key = type_key.lower()

        if "walk" in key:

            return "Walk"

        if "hik" in key:

            return "Hike"

        if "trail" in key:

            return "TrailRun"

        if "swim" in key:

            return "Swim"

        # running, treadmill_running, indoor_running, track_running...
        if "run" in key:

            return "Run"

        return "Other"

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
    def _laps(splits: dict) -> list[dict]:
        """Voltas/blocos do treino (lapDTOs) -> distância, duração, pace e FC
        média por volta. Num treino estruturado são os passos executados; a
        IA os alinha com a prescrição (a prescrição é em TEMPO: 3'/2'...)."""

        items = (
            splits.get("lapDTOs")
            or splits.get("splits")
            or (splits if isinstance(splits, list) else [])
        )

        result = []

        for it in items:

            hr = _num(_first(it, "averageHR", "averageHeartRate"))

            result.append(
                {
                    "distance_m": round(
                        float(_first(it, "distance", default=0) or 0)
                    ),
                    "duration_s": round(
                        float(
                            _first(it, "duration", "movingDuration", default=0)
                            or 0
                        )
                    ),
                    "pace": _speed_to_pace(_first(it, "averageSpeed", default=0)),
                    "avg_hr": int(hr) if hr else None,
                }
            )

        return result

    @staticmethod
    def _km_splits_from_streams(streams: dict) -> list[dict]:
        """Parciais REAIS por km, a partir do stream: distribui as amostras
        de velocidade/FC em baldes de 1 km pela distância acumulada e tira a
        média de cada. Só km COMPLETOS (descarta a sobra final). Formato
        splits_metric do Strava ({distance, average_speed, average_heartrate})
        pra o WorkoutStructureBuilder consumir igual."""

        distance = streams.get("distance") or []

        speed = streams.get("velocity_smooth") or []

        hr = streams.get("heartrate") or []

        if not distance or not speed:

            return []

        n = min(len(distance), len(speed))

        buckets: dict[int, dict] = {}

        for i in range(n):

            km = int((distance[i] or 0) // 1000)

            bucket = buckets.setdefault(km, {"speeds": [], "hrs": []})

            if speed[i]:

                bucket["speeds"].append(speed[i])

            if i < len(hr) and hr[i]:

                bucket["hrs"].append(hr[i])

        total_km = int((distance[n - 1] or 0) // 1000)

        result = []

        for km in range(total_km):

            bucket = buckets.get(km)

            if not bucket or not bucket["speeds"]:

                continue

            result.append(
                {
                    "distance": 1000,
                    "average_speed": (
                        sum(bucket["speeds"]) / len(bucket["speeds"])
                    ),
                    "average_heartrate": (
                        round(sum(bucket["hrs"]) / len(bucket["hrs"]))
                        if bucket["hrs"]
                        else None
                    ),
                }
            )

        return result

    @staticmethod
    def _classify_splits(typed: dict) -> list[dict]:
        """Classifica CADA volta do typed_splits (esforço/recuperação/outra),
        na ordem cronológica -- usada tanto pro IntervalAnalysis exato
        (_exact_interval, só os "effort") quanto pro pareamento
        bloco-a-bloco geral com o plano (_garmin_typed_blocks, guarda TODAS
        as voltas classificadas, inclusive aquecimento/desaquecimento/
        corrida contínua sob "other").

        RWD_* (run-walk-detection do Garmin) fica de fora sempre: é uma
        segmentação PARALELA que soma a distância TOTAL do treino de novo
        (achado real do dump do Mauricio, ver testes) -- incluir duplicaria
        distância/tempo no pareamento."""

        splits = (
            typed.get("splits")
            or typed.get("lapDTOs")
            or (typed if isinstance(typed, list) else [])
        )

        classified = []

        for sp in splits:

            sp_type = str(
                _first(sp, "type", "splitType", default="")
            ).upper()

            if sp_type.startswith("RWD_"):

                continue

            avg_speed = _first(sp, "averageSpeed", default=0)

            hr = _num(_first(sp, "averageHR", "averageHeartRate"))

            max_hr = _num(_first(sp, "maxHR", "maxHeartRate")) or hr

            if _is_effort_type(sp_type):

                kind = "effort"

            elif _is_recovery_type(sp_type):

                kind = "recovery"

            else:

                kind = "other"

            classified.append(
                {
                    "kind": kind,
                    "distance_m": round(
                        float(_first(sp, "distance", default=0) or 0)
                    ),
                    "duration_s": round(
                        float(
                            _first(sp, "duration", "movingDuration", default=0)
                            or 0
                        )
                    ),
                    "pace": _speed_to_pace(avg_speed),
                    "avg_hr": int(hr) if hr else None,
                    "peak_hr": int(max_hr) if max_hr else None,
                    # guardado só pro contraste/filtro; sai dos reps finais
                    "_speed": avg_speed or None,
                }
            )

        return classified

    @staticmethod
    def _exact_interval(
        typed: dict,
        external_coach: bool = False,
    ) -> IntervalAnalysis | None:
        """O PULO DO GATO: monta a IntervalAnalysis a partir das voltas já
        ROTULADAS pelo Garmin (esforço vs recuperação) — reps exatos,
        alinhados ao treino proposto, sem inferência.

        external_coach: aciona o filtro de tiros em ritmo de caminhada
        (voltas do treinador externo não são confiáveis — ver
        [[_drop_walk_paced_efforts]])."""

        classified = GarminActivitySource._classify_splits(typed)

        efforts = [
            {
                "distance_m": c["distance_m"],
                "pace": c["pace"],
                "peak_hr": c["peak_hr"],
                "_speed": c["_speed"],
            }
            for c in classified
            if c["kind"] == "effort"
        ]

        recovery_hrs = [
            c["avg_hr"]
            for c in classified
            if c["kind"] == "recovery" and c["avg_hr"]
        ]

        recovery_speeds = [
            c["_speed"]
            for c in classified
            if c["kind"] == "recovery" and c["_speed"]
        ]

        # treinador externo: descarta os "tiros" que na verdade são caminhada
        # (aquecimento/desaquecimento/pausa que o Garmin rotulou como ACTIVE)
        if external_coach:

            efforts = _drop_walk_paced_efforts(efforts)

        if len(efforts) < 2:

            return None

        effort_speeds = [e["_speed"] for e in efforts if e["_speed"]]

        # reps finais sem o campo interno de velocidade
        efforts = [
            {k: v for k, v in e.items() if k != "_speed"}
            for e in efforts
        ]

        paces = [e["pace"] for e in efforts if e["pace"]]

        peaks = [e["peak_hr"] for e in efforts if e["peak_hr"]]

        avg_peak_hr = round(sum(peaks) / len(peaks)) if peaks else None

        avg_recovery_hr = (
            round(sum(recovery_hrs) / len(recovery_hrs))
            if recovery_hrs
            else None
        )

        # com dado de recuperação, exige contraste real (senão é run-walk /
        # rodagem com pausas que o Garmin rotulou como intervalo). Sem
        # recuperação nenhuma, confia no rótulo (tiro estruturado que
        # empurramos, cujas voltas o Garmin devolve alinhadas).
        if (recovery_hrs or recovery_speeds) and not _real_interval(
            avg_peak_hr, avg_recovery_hr, effort_speeds, recovery_speeds
        ):

            return None

        return IntervalAnalysis(
            rep_count=len(efforts),
            avg_rep_pace=round(sum(paces) / len(paces), 3) if paces else 0,
            avg_peak_hr=avg_peak_hr,
            avg_recovery_hr=avg_recovery_hr,
            reps=efforts,
        )


def _num(value) -> float | None:

    return float(value) if isinstance(value, (int, float)) else None
