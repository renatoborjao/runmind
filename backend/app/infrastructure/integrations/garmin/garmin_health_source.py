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
from app.infrastructure.integrations.garmin.garmin_client import GarminClient


def _hours(seconds) -> float | None:

    if seconds is None:

        return None

    try:

        return round(float(seconds) / 3600, 2)

    except (TypeError, ValueError):

        return None


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

    @staticmethod
    def _apply_vo2max(health: DailyHealth, data) -> None:

        # get_max_metrics devolve uma lista; o VO2max de corrida está em
        # [0]["generic"]["vo2MaxPreciseValue"]
        if not isinstance(data, list) or not data:

            return

        generic = (data[0] or {}).get("generic") or {}

        health.vo2max = generic.get("vo2MaxPreciseValue") or generic.get(
            "vo2MaxValue"
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
