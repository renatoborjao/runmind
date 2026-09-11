"""Puxa o retrato diário de SAÚDE do Garmin (sono, HRV, stress, body
battery, FC repouso, VO2max + os sinais que a Garmin já computa nos relógios
melhores) e mapeia pra DailyHealth. Camada 1: só ingere, sem IA.

Mapeamento ancorado no JSON REAL: os primitivos no dump do FR165 (Renato,
2026-07); os campos PREMIUM (readiness, training status/load balance) no dump
do FR265 (João, 2026-09-05) — o formato populado, antes só suposto, foi
validado ao vivo. Cada endpoint num try isolado — device sem tal métrica,
relógio novo sem baseline, dia sem sono medido: o campo vira None, o snapshot
não quebra.

Readiness vem numa lista (item[0].score/level). Training status/load balance
vêm ANINHADOS por deviceId: `mostRecentTrainingStatus.latestTrainingStatusData
[<deviceId>].trainingStatusFeedbackPhrase` (ex.: "PRODUCTIVE_3") e
`mostRecentTrainingLoadBalance.metricsTrainingLoadBalanceDTOMap[<deviceId>].
trainingBalanceFeedbackPhrase` (ex.: "AEROBIC_HIGH_SHORTAGE"). No FR165 ambos
vêm vazios (None), sem quebrar."""

import re

from app.domain.entities.daily_health import DailyHealth
from app.domain.entities.race_prediction import RacePrediction
from app.infrastructure.integrations.garmin.garmin_client import GarminClient


def _hours(seconds) -> float | None:

    if seconds is None:

        return None

    try:

        return round(float(seconds) / 3600, 2)

    except (TypeError, ValueError):

        return None


def _as_int(value) -> int | None:
    """Número (int/float) arredondado pra int, ou None — passos, calorias e
    SpO2 às vezes vêm como float na API."""

    if not isinstance(value, (int, float)):

        return None

    return round(value)


def _as_float(value) -> float | None:
    """Número com 1 casa (respiração), ou None."""

    if not isinstance(value, (int, float)):

        return None

    return round(float(value), 1)


def _set_if(health: "DailyHealth", attr: str, value) -> None:
    """Grava só quando há valor — assim um endpoint que não mediu (None) nunca
    apaga um dado que outro já trouxe (user_summary × respiration × spo2 se
    completam, ordem não importa)."""

    if value is not None:

        setattr(health, attr, value)


class GarminHealthSource:

    @staticmethod
    def fetch(profile: str, day: str) -> DailyHealth:
        """Retrato de saúde do atleta no dia `day` (YYYY-MM-DD)."""

        garmin = GarminClient.connect(profile)

        health = DailyHealth(date=day)

        GarminHealthSource._apply_sleep(
            health, GarminHealthSource._safe(lambda: garmin.get_sleep_data(day))
        )

        GarminHealthSource._apply_hrv(
            health, GarminHealthSource._safe(lambda: garmin.get_hrv_data(day))
        )

        GarminHealthSource._apply_stress(
            health,
            GarminHealthSource._safe(lambda: garmin.get_all_day_stress(day)),
        )

        GarminHealthSource._apply_vo2max(
            health, GarminHealthSource._safe(lambda: garmin.get_max_metrics(day))
        )

        GarminHealthSource._apply_readiness(
            health,
            GarminHealthSource._safe(
                lambda: garmin.get_training_readiness(day)
            ),
        )

        GarminHealthSource._apply_training_status(
            health,
            GarminHealthSource._safe(lambda: garmin.get_training_status(day)),
        )

        # tier-2: carga de vida + body battery + respiração + SpO2. O
        # user_summary consolida quase tudo (1 chamada); os dedicados agregam
        # só as médias de SONO (respiração/SpO2 dormindo = sinal de recuperação
        # que o summary não traz). Cada um num _safe — device sem a métrica
        # vira None, não derruba o snapshot.
        GarminHealthSource._apply_user_summary(
            health, GarminHealthSource._safe(lambda: garmin.get_user_summary(day))
        )

        GarminHealthSource._apply_respiration(
            health,
            GarminHealthSource._safe(lambda: garmin.get_respiration_data(day)),
        )

        GarminHealthSource._apply_spo2(
            health, GarminHealthSource._safe(lambda: garmin.get_spo2_data(day))
        )

        return health

    # ------------------------------------------------------------------

    @staticmethod
    def _safe(fn):
        """Chama o endpoint tolerando falha/ausência — devolve o resultado
        ou None, nunca levanta (um device sem a métrica não pode derrubar o
        resto do snapshot)."""

        try:

            return fn()

        except Exception:  # noqa: BLE001 — endpoint ausente/instável vira None

            return None

    @staticmethod
    def _apply_sleep(health: DailyHealth, data) -> None:

        if not isinstance(data, dict):

            return

        dto = data.get("dailySleepDTO") or {}

        health.sleep_hours = _hours(dto.get("sleepTimeSeconds"))

        health.deep_sleep_hours = _hours(dto.get("deepSleepSeconds"))

        health.rem_sleep_hours = _hours(dto.get("remSleepSeconds"))

        health.light_sleep_hours = _hours(dto.get("lightSleepSeconds"))

        health.awake_hours = _hours(dto.get("awakeSleepSeconds"))

        scores = dto.get("sleepScores") or {}

        overall = scores.get("overall") or {}

        health.sleep_score = overall.get("value")

        # estes vêm na RAIZ do sleep_data, não no dailySleepDTO
        health.body_battery_change = data.get("bodyBatteryChange")

        health.resting_hr = data.get("restingHeartRate")

    @staticmethod
    def _apply_hrv(health: DailyHealth, data) -> None:

        if not isinstance(data, dict):

            return

        summary = data.get("hrvSummary") or {}

        health.hrv_last_night = summary.get("lastNightAvg")

        health.hrv_weekly_avg = summary.get("weeklyAvg")

        # "NONE" enquanto o relógio novo ainda não tem baseline: guarda como
        # está (a leitura decide o que fazer com "sem status ainda")
        health.hrv_status = summary.get("status")

    @staticmethod
    def _apply_stress(health: DailyHealth, data) -> None:

        if not isinstance(data, dict):

            return

        health.stress_avg = data.get("avgStressLevel")

        health.stress_max = data.get("maxStressLevel")

    # ------------------------------------------------------------------
    # tier-2: carga de vida, body battery, respiração, SpO2
    # ------------------------------------------------------------------

    # campos derivados do get_user_summary (usados no fetch diário E na
    # varredura barata que enriquece dias recentes — uma chamada só).
    _USER_SUMMARY_FIELDS = (
        "steps", "steps_goal", "active_calories",
        "intensity_minutes_moderate", "intensity_minutes_vigorous",
        "intensity_minutes_goal", "body_battery_most_recent",
        "body_battery_at_wake", "body_battery_high", "body_battery_low",
        "respiration_waking_avg", "respiration_high", "respiration_low",
        "spo2_avg", "spo2_low",
    )

    @staticmethod
    def _apply_user_summary(health: DailyHealth, data) -> None:
        """Resumo diário: carga de vida (passos/calorias/intensity minutes),
        body battery ao longo do dia e — de brinde — respiração de vigília e
        SpO2 (as médias de SONO vêm dos endpoints dedicados)."""

        if not isinstance(data, dict):

            return

        # carga de vida (esforço fora do treino)
        _set_if(health, "steps", _as_int(data.get("totalSteps")))
        _set_if(health, "steps_goal", _as_int(data.get("dailyStepGoal")))
        _set_if(health, "active_calories",
                _as_int(data.get("activeKilocalories")))
        _set_if(health, "intensity_minutes_moderate",
                _as_int(data.get("moderateIntensityMinutes")))
        _set_if(health, "intensity_minutes_vigorous",
                _as_int(data.get("vigorousIntensityMinutes")))
        _set_if(health, "intensity_minutes_goal",
                _as_int(data.get("intensityMinutesGoal")))

        # body battery: o tanque ao longo do dia
        _set_if(health, "body_battery_most_recent",
                _as_int(data.get("bodyBatteryMostRecentValue")))
        _set_if(health, "body_battery_at_wake",
                _as_int(data.get("bodyBatteryAtWakeTime")))
        _set_if(health, "body_battery_high",
                _as_int(data.get("bodyBatteryHighestValue")))
        _set_if(health, "body_battery_low",
                _as_int(data.get("bodyBatteryLowestValue")))

        # respiração/SpO2 de vigília (o summary usa 'Spo2' minúsculo)
        _set_if(health, "respiration_waking_avg",
                _as_float(data.get("avgWakingRespirationValue")))
        _set_if(health, "respiration_high",
                _as_float(data.get("highestRespirationValue")))
        _set_if(health, "respiration_low",
                _as_float(data.get("lowestRespirationValue")))
        _set_if(health, "spo2_avg", _as_int(data.get("averageSpo2")))
        _set_if(health, "spo2_low", _as_int(data.get("lowestSpo2")))

    @staticmethod
    def _apply_respiration(health: DailyHealth, data) -> None:
        """Endpoint dedicado: agrega a média de respiração no SONO (a de vigília
        e pico o summary já traz; aqui refina/completa). Chaves com 'Respiration'
        maiúsculo."""

        if not isinstance(data, dict):

            return

        _set_if(health, "respiration_sleep_avg",
                _as_float(data.get("avgSleepRespirationValue")))
        _set_if(health, "respiration_waking_avg",
                _as_float(data.get("avgWakingRespirationValue")))
        _set_if(health, "respiration_high",
                _as_float(data.get("highestRespirationValue")))
        _set_if(health, "respiration_low",
                _as_float(data.get("lowestRespirationValue")))

    @staticmethod
    def _apply_spo2(health: DailyHealth, data) -> None:
        """Endpoint dedicado: SpO2 média/mínima e a média de SONO. Chaves com
        'SpO2' maiúsculo (o summary usa 'Spo2' — API inconsistente, por isso os
        dois mapeamentos)."""

        if not isinstance(data, dict):

            return

        _set_if(health, "spo2_avg", _as_int(data.get("averageSpO2")))
        _set_if(health, "spo2_sleep_avg", _as_int(data.get("avgSleepSpO2")))
        _set_if(health, "spo2_low", _as_int(data.get("lowestSpO2")))

    @staticmethod
    def body_context_for(garmin, day: str) -> dict:
        """Só a carga de vida + body battery de um dia (1 chamada,
        get_user_summary), pra MESCLAR em snapshots recentes sem re-baixar
        sono/HRV/stress. Devolve só os campos preenchidos (não-None)."""

        data = GarminHealthSource._safe(lambda: garmin.get_user_summary(day))

        tmp = DailyHealth(date=day)

        GarminHealthSource._apply_user_summary(tmp, data)

        return {
            f: getattr(tmp, f)
            for f in GarminHealthSource._USER_SUMMARY_FIELDS
            if getattr(tmp, f) is not None
        }

    @staticmethod
    def _apply_vo2max(health: DailyHealth, data) -> None:

        health.vo2max = GarminHealthSource._extract_vo2max(data)

    @staticmethod
    def _extract_vo2max(data) -> float | None:
        """VO₂máx de corrida do payload de get_max_metrics (uma lista;
        [0]['generic']['vo2MaxPreciseValue']). Puro/testável. None quando o
        dia não tem medição gravada (o Garmin só recalcula esporadicamente —
        por isso a coleta precisa VARRER dias, não olhar só 'ontem')."""

        if not isinstance(data, list) or not data:

            return None

        generic = (data[0] or {}).get("generic") or {}

        return generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")

    @staticmethod
    def vo2max_for(garmin, day: str) -> float | None:
        """Só o VO₂máx de um dia (chamada barata e isolada) — pra a varredura
        que preenche as lacunas da série sem re-baixar sono/HRV/stress."""

        data = GarminHealthSource._safe(lambda: garmin.get_max_metrics(day))

        return GarminHealthSource._extract_vo2max(data)

    @staticmethod
    def race_predictions_for(garmin) -> RacePrediction:
        """Previsão de prova ATUAL do Garmin (5K/10K/meia/maratona). Sem args:
        a API devolve a projeção mais recente. Campos ausentes viram None."""

        data = GarminHealthSource._safe(lambda: garmin.get_race_predictions())

        return GarminHealthSource._extract_race_predictions(data)

    @staticmethod
    def _extract_race_predictions(data) -> RacePrediction:
        """Payload de get_race_predictions -> RacePrediction. Puro/testável."""

        if not isinstance(data, dict):

            return RacePrediction()

        def _int(key):

            value = data.get(key)

            return int(value) if isinstance(value, (int, float)) else None

        return RacePrediction(
            date=data.get("calendarDate"),
            time_5k_sec=_int("time5K"),
            time_10k_sec=_int("time10K"),
            time_half_sec=_int("timeHalfMarathon"),
            time_marathon_sec=_int("timeMarathon"),
        )

    @staticmethod
    def _apply_readiness(health: DailyHealth, data) -> None:

        # vazio no FR165; no FR265 é uma lista com score/level (validado ao
        # vivo, João 2026-09-05: item[0] tem 'score' e 'level').
        if not isinstance(data, list) or not data:

            return

        item = data[0] or {}

        health.readiness_score = item.get("score")

        health.readiness_level = item.get("level")

    @staticmethod
    def _apply_training_status(health: DailyHealth, data) -> None:

        # tudo None no FR165. No FR265 (validado ao vivo) os valores vêm
        # ANINHADOS por deviceId — desce até o device (primário quando marcado)
        # e pega a frase de feedback, mais legível que o código inteiro.
        if not isinstance(data, dict):

            return

        status_dto = GarminHealthSource._primary_device(
            data.get("mostRecentTrainingStatus"), "latestTrainingStatusData"
        )

        if status_dto:

            health.training_status = GarminHealthSource._status_label(
                status_dto.get("trainingStatusFeedbackPhrase")
            )

        balance_dto = GarminHealthSource._primary_device(
            data.get("mostRecentTrainingLoadBalance"),
            "metricsTrainingLoadBalanceDTOMap",
        )

        if balance_dto:

            phrase = balance_dto.get("trainingBalanceFeedbackPhrase")

            health.training_load_balance = (
                phrase if isinstance(phrase, str) else None
            )

    @staticmethod
    def _primary_device(container, map_key: str):
        """Do container aninhado por deviceId (`{map_key: {<id>: {...}}}`),
        devolve o DTO do device PRIMÁRIO (ou o primeiro que houver). None se o
        formato não bater (FR165 manda o container None) — nunca quebra.
        Aceita também um container que já venha como string direta (defensivo:
        firmware/futuro), devolvendo-a embrulhada pra o chamador extrair."""

        if isinstance(container, str):

            return {"trainingStatusFeedbackPhrase": container,
                    "trainingBalanceFeedbackPhrase": container}

        if not isinstance(container, dict):

            return None

        by_device = container.get(map_key)

        if not isinstance(by_device, dict) or not by_device:

            return None

        devices = [d for d in by_device.values() if isinstance(d, dict)]

        for dto in devices:

            if dto.get("primaryTrainingDevice"):

                return dto

        return devices[0] if devices else None

    @staticmethod
    def _status_label(phrase):
        """Normaliza a frase de status da Garmin ("PRODUCTIVE_3") pro rótulo
        canônico ("PRODUCTIVE") que o formatter traduz. "NO_STATUS_x" (relógio
        ainda sem base suficiente) e "NONE" viram None — nada a mostrar."""

        if not isinstance(phrase, str):

            return None

        base = re.sub(r"_\d+$", "", phrase).upper()

        if base in ("NO_STATUS", "NONE", ""):

            return None

        return base
