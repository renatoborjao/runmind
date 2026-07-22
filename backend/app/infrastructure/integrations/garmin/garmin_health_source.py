"""Puxa o retrato diário de SAÚDE do Garmin (sono, HRV, stress, body
battery, FC repouso, VO2max + os sinais que a Garmin já computa nos relógios
melhores) e mapeia pra DailyHealth. Camada 1: só ingere, sem IA.

Mapeamento ancorado no JSON REAL (dump da conta do Renato, FR165, 2026-07):
cada endpoint num try isolado — device sem tal métrica, relógio novo sem
baseline, dia sem sono medido: o campo vira None, o snapshot não quebra.

Os campos que a Garmin só calcula nos relógios melhores (readiness,
training_status) vêm None no FR165; o formato POPULADO deles ainda não foi
validado contra um device premium — a extração é best-effort e defensiva
(nunca quebra), a validar quando um atleta com FR265/965 conectar."""

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

        # vazio no FR165; nos relógios melhores é uma lista com score/level.
        # Formato populado a validar num device premium — extração defensiva.
        if not isinstance(data, list) or not data:

            return

        item = data[0] or {}

        health.readiness_score = item.get("score")

        health.readiness_level = item.get("level")

    @staticmethod
    def _apply_training_status(health: DailyHealth, data) -> None:

        # tudo None no FR165. Em device premium, mostRecentTrainingStatus e
        # mostRecentTrainingLoadBalance vêm preenchidos (formato exato a
        # validar) — guarda um rótulo legível quando dá, None quando não.
        if not isinstance(data, dict):

            return

        health.training_status = GarminHealthSource._label(
            data.get("mostRecentTrainingStatus")
        )

        health.training_load_balance = GarminHealthSource._label(
            data.get("mostRecentTrainingLoadBalance")
        )

    @staticmethod
    def _label(value):
        """Reduz um valor Garmin (string direta OU DTO aninhado) a um rótulo
        legível, defensivo — None se não der pra extrair."""

        if value is None:

            return None

        if isinstance(value, str):

            return value

        if isinstance(value, dict):

            for key in (
                "trainingStatus",
                "trainingStatusKey",
                "status",
                "key",
            ):

                found = value.get(key)

                if isinstance(found, str):

                    return found

        return None
