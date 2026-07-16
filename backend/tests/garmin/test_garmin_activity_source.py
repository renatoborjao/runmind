"""Testa o mapeamento Garmin -> IntervalAnalysis exata e os streams. Os
nomes de campo aqui seguem o formato conhecido do Garmin Connect; a
verificação final é contra uma atividade real (garmin_dump.py)."""

from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)


def test_exact_interval_from_typed_splits():
    """6x800: as voltas ROTULADAS viram reps exatos, sem inferência."""

    typed = {
        "splits": [
            {"type": "WARMUP", "distance": 2000, "averageSpeed": 2.6,
             "averageHR": 130},
            # 3 tiros + recuperações (esforço=INTERVAL, pausa=RECOVERY)
            {"type": "INTERVAL", "distance": 800, "averageSpeed": 3.5,
             "averageHR": 165, "maxHR": 170},
            {"type": "RECOVERY", "distance": 400, "averageSpeed": 2.4,
             "averageHR": 140},
            {"type": "INTERVAL", "distance": 800, "averageSpeed": 3.5,
             "averageHR": 168, "maxHR": 172},
            {"type": "RECOVERY", "distance": 400, "averageSpeed": 2.4,
             "averageHR": 138},
            {"type": "INTERVAL", "distance": 800, "averageSpeed": 3.5,
             "averageHR": 169, "maxHR": 174},
            {"type": "COOLDOWN", "distance": 1500, "averageSpeed": 2.6,
             "averageHR": 128},
        ]
    }

    interval = GarminActivitySource._exact_interval(typed)

    assert interval is not None
    assert interval.rep_count == 3  # exato: 3 tiros, nem 2 nem 4
    assert len(interval.reps) == 3
    assert interval.reps[0]["distance_m"] == 800
    # FC de recuperação vem das voltas RECOVERY
    assert interval.avg_recovery_hr == 139  # (140+138)/2 ~ 139
    assert interval.avg_peak_hr == 172  # (170+172+174)/3 = 172


def test_no_interval_when_less_than_two_efforts():

    typed = {"splits": [
        {"type": "RUN", "distance": 8000, "averageSpeed": 2.8},
    ]}

    assert GarminActivitySource._exact_interval(typed) is None


def test_exact_interval_handles_real_suffixed_types():
    """Voltas reais do Garmin vêm com sufixo: INTERVAL_ACTIVE (esforço) e
    INTERVAL_RECOVERY (pausa). O matching por substring cobre — e não
    confunde RECOVERY com esforço."""

    typed = {"splits": [
        {"type": "INTERVAL_ACTIVE", "distance": 800, "averageSpeed": 3.5,
         "averageHR": 165, "maxHR": 170},
        {"type": "INTERVAL_RECOVERY", "distance": 400, "averageSpeed": 2.4,
         "averageHR": 140},
        {"type": "INTERVAL_ACTIVE", "distance": 800, "averageSpeed": 3.5,
         "averageHR": 168, "maxHR": 172},
        {"type": "INTERVAL_RECOVERY", "distance": 400, "averageSpeed": 2.4,
         "averageHR": 138},
    ]}

    interval = GarminActivitySource._exact_interval(typed)

    assert interval.rep_count == 2
    assert interval.avg_recovery_hr == 139
    assert interval.avg_peak_hr == 171


def test_labeled_interval_without_contrast_is_rejected():
    """Bug do Mauricio: run-walk que o Garmin rotula como INTERVAL_ACTIVE/REST,
    mas sem contraste real (FC quase não cai, esforço mal mais rápido que a
    recuperação) -> NÃO é intervalado (cai no gate)."""

    typed = {"splits": [
        # esforço ~2.8 m/s, "recuperação" ~2.53 (ratio ~1.11 < 1.15) e FC
        # swing ~8 (< 12) -- os dois abaixo do gate
        {"type": "INTERVAL_ACTIVE", "distance": 600, "averageSpeed": 2.8,
         "averageHR": 150, "maxHR": 159},
        {"type": "INTERVAL_REST", "distance": 300, "averageSpeed": 2.55,
         "averageHR": 151},
        {"type": "INTERVAL_ACTIVE", "distance": 550, "averageSpeed": 2.8,
         "averageHR": 155, "maxHR": 160},
        {"type": "INTERVAL_REST", "distance": 300, "averageSpeed": 2.5,
         "averageHR": 152},
    ]}

    assert GarminActivitySource._exact_interval(typed) is None


def test_labeled_interval_with_hr_response_is_kept():
    """Contraste real de FC (esforço pico bem acima da recuperação) -> mantém
    como intervalado mesmo sem grande diferença de pace."""

    typed = {"splits": [
        {"type": "INTERVAL_ACTIVE", "distance": 800, "averageSpeed": 3.0,
         "averageHR": 165, "maxHR": 172},
        {"type": "INTERVAL_RECOVERY", "distance": 400, "averageSpeed": 2.6,
         "averageHR": 130},
        {"type": "INTERVAL_ACTIVE", "distance": 800, "averageSpeed": 3.0,
         "averageHR": 167, "maxHR": 174},
        {"type": "INTERVAL_RECOVERY", "distance": 400, "averageSpeed": 2.6,
         "averageHR": 128},
    ]}

    interval = GarminActivitySource._exact_interval(typed)

    assert interval is not None
    assert interval.rep_count == 2


def _mauricio_16_07_splits() -> dict:
    """Treino real do Mauricio (16/07): aquecimento + 4×2' + 4×1' + CAM10'.
    A CAM10' final (1328 m a ~7:37) veio rotulada INTERVAL_ACTIVE pelo
    Garmin (treinador externo, voltas auto/manuais) -> virava o "Tiro 9"
    fantasma. Esforços e caminhadas alternados."""

    def effort(dist, speed, max_hr):
        return {
            "type": "INTERVAL_ACTIVE", "distance": dist,
            "averageSpeed": speed, "averageHR": max_hr - 5, "maxHR": max_hr,
        }

    def walk():
        return {
            "type": "INTERVAL_RECOVERY", "distance": 250,
            "averageSpeed": 1.9, "averageHR": 160,
        }

    reps = [
        effort(378, 3.155, 148),  # 5:17
        effort(402, 3.344, 162),  # 4:59
        effort(407, 3.390, 165),  # 4:55
        effort(393, 3.279, 161),  # 5:05
        effort(213, 3.546, 172),  # 4:42
        effort(213, 3.546, 170),  # 4:42
        effort(201, 3.356, 160),  # 4:58
        effort(204, 3.401, 165),  # 4:54
    ]

    splits = []
    for rep in reps:
        splits.append(rep)
        splits.append(walk())

    # a CAM10' final mal rotulada: ~1328 m a 7:37 (2.188 m/s)
    splits.append(effort(1328, 2.188, 173))

    return {"splits": splits}


def test_external_coach_drops_walk_paced_phantom_shot():
    """Treinador externo: a CAM10' (7:37, ritmo de caminhada) NÃO conta como
    tiro — some o "Tiro 9" fantasma e o pace médio para de ser poluído."""

    typed = _mauricio_16_07_splits()

    interval = GarminActivitySource._exact_interval(typed, external_coach=True)

    assert interval is not None
    assert interval.rep_count == 8  # os 4×2' + 4×1', sem a caminhada

    # nenhum "tiro" com distância/pace de caminhada sobrou
    assert all(rep["distance_m"] <= 700 for rep in interval.reps)
    assert max(rep["pace"] for rep in interval.reps) < 6.0  # nada de 7:37


def test_non_external_path_is_untouched():
    """Sem treinador externo (treino que NÓS empurramos): comportamento
    intacto — o filtro não roda. Aqui a mesma volta caminhada mal rotulada
    ainda entraria; na prática o nosso push manda COOLDOWN, que já é
    excluído — por isso o filtro é exclusivo do externo."""

    typed = _mauricio_16_07_splits()

    interval = GarminActivitySource._exact_interval(typed, external_coach=False)

    assert interval is not None
    assert interval.rep_count == 9  # sem filtro, a caminhada entra


def test_longao_typed_splits_do_not_become_interval():
    """Longão real (typed_splits do renato2 hoje): 1 bloco INTERVAL_ACTIVE +
    voltas RWD_* de run-walk-detection -> NÃO é intervalado."""

    typed = {"splits": [
        {"type": "RWD_RUN", "distance": 8261, "averageSpeed": 2.61,
         "averageHR": 160},
        {"type": "INTERVAL_ACTIVE", "distance": 12212, "averageSpeed": 2.62,
         "averageHR": 160, "maxHR": 169},
        {"type": "RWD_STAND", "distance": None, "averageSpeed": 0},
        {"type": "RWD_WALK", "distance": 17, "averageSpeed": 2.67,
         "averageHR": 143},
        {"type": "RWD_RUN", "distance": 3933, "averageSpeed": 2.63,
         "averageHR": 162},
    ]}

    assert GarminActivitySource._exact_interval(typed) is None


def test_to_activity_reads_nested_dtos():
    """get_activity devolve DTOs aninhados (summaryDTO/activityTypeDTO/
    timeZoneUnitDTO) — regressão do bug que lia campos planos e zerava tudo."""

    summary = {
        "activityId": 123,
        "activityName": "Longão 12km",
        "activityTypeDTO": {"typeKey": "running"},
        "timeZoneUnitDTO": {"timeZone": "America/Sao_Paulo"},
        "summaryDTO": {
            "distance": 12212.34, "movingDuration": 4656,
            "elapsedDuration": 4709, "duration": 4661,
            "averageSpeed": 2.62, "maxSpeed": 3.16,
            "averageHR": 160, "maxHR": 169, "elevationGain": 39,
            "maxElevation": 762, "minElevation": 749,
            "startLatitude": -23.5, "startLongitude": -46.6,
            "startTimeGMT": "2026-07-11T10:00:27.0",
        },
    }

    act = GarminActivitySource._to_activity(123, summary, dict(summary))

    assert act.name == "Longão 12km"
    assert act.sport == "Run"
    assert act.timezone == "America/Sao_Paulo"
    assert act.distance == 12212.34
    assert act.moving_time == 4656
    assert act.average_heartrate == 160.0
    assert act.max_heartrate == 169.0
    assert act.elevation_gain == 39.0
    assert act.start_latitude == -23.5


def test_gps_activity_is_never_treadmill():
    """Treino com GPS (coordenada de partida) NUNCA é esteira, mesmo com
    isIndoor/typeKey de esteira — glitch de perda de GPS no meio do treino
    (caso real do Renato: correu no parque, relógio quebrou/reiniciou)."""

    summary = {
        "activityId": 1, "activityName": "Parque",
        "activityTypeDTO": {"typeKey": "treadmill_running"},
        "summaryDTO": {
            "distance": 6000, "duration": 2000, "averageSpeed": 3.0,
            "isIndoor": True,
            "startLatitude": -23.5, "startLongitude": -46.7,
            "startTimeGMT": "2026-07-14T10:00:00.0",
        },
    }

    act = GarminActivitySource._to_activity(1, summary, dict(summary))

    assert act.raw["trainer"] is False


def test_indoor_activity_without_gps_is_treadmill():
    """Sem GPS + tipo/flag de esteira: aí sim é esteira (distância estimada)."""

    summary = {
        "activityId": 2, "activityName": "Esteira",
        "activityTypeDTO": {"typeKey": "treadmill_running"},
        "summaryDTO": {
            "distance": 5000, "duration": 1800, "averageSpeed": 2.7,
            "startTimeGMT": "2026-07-14T10:00:00.0",
        },
    }

    act = GarminActivitySource._to_activity(2, summary, dict(summary))

    assert act.raw["trainer"] is True


def test_start_date_uses_local_wall_clock_not_utc():
    """Garmin manda startTimeLocal (07:00 BRT) e startTimeGMT (10:00 UTC).
    Usamos a hora LOCAL (igual ao start_date_local do Strava) pra o dia da
    semana bater e casar com a versão Strava do mesmo treino — não os +3h
    do GMT, que jogariam corrida perto da meia-noite pro dia errado."""

    summary = {
        "activityId": 9,
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "distance": 5000, "movingDuration": 1800, "duration": 1800,
            "startTimeLocal": "2026-07-11T07:00:27.0",
            "startTimeGMT": "2026-07-11T10:00:27.0",
        },
    }

    act = GarminActivitySource._to_activity(9, summary, dict(summary))

    assert act.start_date.hour == 7          # local, não 10 (UTC)
    assert act.start_date.date().isoformat() == "2026-07-11"


def test_rich_metrics_keeps_only_present_fields():

    summary_dto = {
        "averageRunCadence": 162, "trainingEffect": 5.0,
        "trainingEffectLabel": "LACTATE_THRESHOLD", "directWorkoutRpe": 50,
        "averagePower": 328, "somethingUnmapped": 1,
        # ausentes: averageTemperature, maxPower...
    }

    metrics = GarminActivitySource._rich_metrics(summary_dto)

    assert metrics["avg_cadence"] == 162
    assert metrics["training_effect_label"] == "LACTATE_THRESHOLD"
    assert metrics["workout_rpe"] == 50
    assert metrics["avg_power"] == 328
    # campo não mapeado não entra; campo ausente não vira None
    assert "somethingUnmapped" not in metrics
    assert "avg_temperature" not in metrics


def test_streams_from_details_parallel_arrays():

    details = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "directSpeed"},
            {"metricsIndex": 1, "key": "directHeartRate"},
            {"metricsIndex": 2, "key": "sumDistance"},
        ],
        "activityDetailMetrics": [
            {"metrics": [3.5, 165, 100]},
            {"metrics": [3.4, 166, 110]},
        ],
    }

    streams = GarminActivitySource._streams(details)

    assert streams["velocity_smooth"] == [3.5, 3.4]
    assert streams["heartrate"] == [165, 166]
    assert streams["distance"] == [100, 110]


def test_km_splits_computed_from_stream_not_laps():
    """Parciais por km saem do STREAM (distância + velocidade + FC), em
    baldes de 1 km — não das lapDTOs (que num treino estruturado são voltas
    de duração, não por-km: o bug do Mauricio)."""

    streams = {
        "distance": [0, 500, 1000, 1500, 2000, 2500],
        "velocity_smooth": [3.0, 3.0, 2.5, 2.5, 4.0, 4.0],
        "heartrate": [150, 152, 145, 147, 165, 167],
    }

    splits = GarminActivitySource._km_splits_from_streams(streams)

    # 2.5 km -> 2 km COMPLETOS (a sobra de 500m é descartada)
    assert len(splits) == 2
    assert splits[0]["distance"] == 1000
    assert splits[0]["average_speed"] == 3.0
    assert splits[0]["average_heartrate"] == 151     # média de 150 e 152
    assert splits[1]["average_speed"] == 2.5
    assert splits[1]["average_heartrate"] == 146


def test_laps_maps_lapdtos_to_blocks_with_duration():
    """Voltas do treino estruturado: duração é a chave (prescrição é em
    tempo, 3'/2') + distância + pace + FC por bloco."""

    splits = {"lapDTOs": [
        {"distance": 548, "duration": 180, "averageSpeed": 3.05,
         "averageHR": 144},
        {"distance": 311, "duration": 120, "averageSpeed": 2.59,
         "averageHR": 141},
    ]}

    laps = GarminActivitySource._laps(splits)

    assert laps[0]["duration_s"] == 180
    assert laps[0]["distance_m"] == 548
    assert laps[0]["avg_hr"] == 144
    assert laps[0]["pace"]
    assert laps[1]["duration_s"] == 120


def test_km_splits_from_streams_empty_when_no_data():

    assert GarminActivitySource._km_splits_from_streams({}) == []
    assert GarminActivitySource._km_splits_from_streams(
        {"distance": [], "velocity_smooth": []}
    ) == []


def test_sport_mapping():

    assert GarminActivitySource._sport("running") == "Run"
    assert GarminActivitySource._sport("treadmill_running") == "Run"
    assert GarminActivitySource._sport("trail_running") == "TrailRun"
    assert GarminActivitySource._sport("walking") == "Walk"


def test_structure_builder_prefers_exact_garmin_interval():
    """Quando o raw traz _garmin_interval (voltas rotuladas), o builder usa
    ele em vez do detector fuzzy por stream."""

    from datetime import datetime

    from app.application.history.workout_structure_builder import (
        WorkoutStructureBuilder,
    )
    from app.domain.entities.activity import Activity
    from app.domain.entities.interval_analysis import IntervalAnalysis

    exact = IntervalAnalysis(
        rep_count=6,
        avg_rep_pace=4.75,
        avg_peak_hr=170,
        avg_recovery_hr=138,
        reps=[{"distance_m": 800, "pace": 4.75, "peak_hr": 170}] * 6,
    )

    activity = Activity(
        id=1, name="Tiros", sport="Run",
        start_date=datetime(2026, 7, 14, 7, 0, 0), timezone="UTC",
        distance=9000, moving_time=2700, elapsed_time=2700,
        average_speed=3.3, max_speed=3.6,
        average_heartrate=150, max_heartrate=174,
        elevation_gain=10, elevation_high=None, elevation_low=None,
        start_latitude=None, start_longitude=None,
        end_latitude=None, end_longitude=None,
        kudos=0, comments=0, suffer_score=None,
        raw={"_garmin_interval": exact, "_streams": {}},
    )

    structure = WorkoutStructureBuilder.build(activity)

    assert structure.interval is exact
    assert structure.interval.rep_count == 6
    assert structure.is_interval is True
