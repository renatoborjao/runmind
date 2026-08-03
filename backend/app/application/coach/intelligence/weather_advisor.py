"""Clima no plano (ANTECIPA): quando o dia do treino vem quente, o coach avisa
ANTES — melhor janela pra correr, segurar o pace (calor derruba o ritmo no mesmo
esforço) e hidratar. Fonte: open-meteo (grátis, sem chave, open-source —
[[feedback_free_tools_preference]]); localização pelo GPS do último treino.
Best-effort: sem coordenada / API fora / dia ameno = nada (silêncio, sem ruído).
Ver [[project_analise_treino_hibrida]] (o EF já normaliza calor na análise)."""

from datetime import date

import httpx

_API = "https://api.open-meteo.com/v1/forecast"

# sensação térmica (°C) a partir da qual o calor pesa no treino
_HOT = 28.0

# janela de horas do dia (local) em que faz sentido treinar — pra achar a mais
# fresca e medir o pico de calor
_DAY_START_H = 5
_DAY_END_H = 20


class WeatherAdvisor:

    @staticmethod
    async def advice(profile: str, target_date: date) -> str | None:
        """Linha amigável pro atleta sobre o clima do dia do treino, ou None
        quando não há coordenada, a API falha, ou o dia está ameno."""

        try:

            coords = await WeatherAdvisor._coords(profile)

            if coords is None:

                return None

            hours = await WeatherAdvisor._fetch(coords[0], coords[1], target_date)

            if not hours:

                return None

            return WeatherAdvisor._build(hours)

        except Exception as e:

            print(f"Clima falhou p/ '{profile}': {e}")

            return None

    # ------------------------------------------------------------------

    @staticmethod
    async def _coords(profile: str) -> tuple[float, float] | None:
        """Lat/lon do treino MAIS RECENTE com GPS (o arquivo permanente não
        guarda coordenada; a janela recente do Strava sim)."""

        from app.application.use_cases.load_training_history import (
            LoadTrainingHistory,
        )

        history = await LoadTrainingHistory.execute(profile=profile)

        for activity in reversed(history.activities):

            if (
                activity.start_latitude is not None
                and activity.start_longitude is not None
            ):

                return activity.start_latitude, activity.start_longitude

        return None

    @staticmethod
    async def _fetch(lat: float, lon: float, target_date: date) -> list[dict]:
        """Previsão HORÁRIA (sensação térmica + prob. de chuva) do dia alvo, no
        fuso local do ponto. Lista de {hour, feels, rain}."""

        iso = target_date.isoformat()

        params = {
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "hourly": "apparent_temperature,precipitation_probability",
            "timezone": "auto",
            "start_date": iso,
            "end_date": iso,
        }

        async with httpx.AsyncClient(timeout=6) as client:

            resp = await client.get(_API, params=params)

            resp.raise_for_status()

            data = resp.json()

        hourly = data.get("hourly") or {}

        times = hourly.get("time") or []

        feels = hourly.get("apparent_temperature") or []

        rain = hourly.get("precipitation_probability") or []

        out = []

        for i, stamp in enumerate(times):

            # stamp = "2026-08-04T15:00"
            try:

                hour = int(stamp[11:13])

            except (ValueError, IndexError):

                continue

            if _DAY_START_H <= hour <= _DAY_END_H and i < len(feels):

                out.append(
                    {
                        "hour": hour,
                        "feels": feels[i],
                        "rain": rain[i] if i < len(rain) else None,
                    }
                )

        return out

    @staticmethod
    def _build(hours: list[dict]) -> str | None:
        """Monta o aviso a partir das horas de treino do dia. None se ameno."""

        valid = [h for h in hours if h["feels"] is not None]

        if not valid:

            return None

        peak = max(valid, key=lambda h: h["feels"])

        if peak["feels"] < _HOT:

            return None  # dia ameno: sem aviso

        coolest = min(valid, key=lambda h: h["feels"])

        ease, extra = WeatherAdvisor._pace_caution(peak["feels"])

        return (
            f"🌡️ Hoje esquenta: sensação de até ~{round(peak['feels'])}° "
            f"(por volta das {peak['hour']}h). Se der, corra mais cedo "
            f"(~{coolest['hour']}h, ~{round(coolest['feels'])}°); "
            f"segura o pace {ease} mais leve{extra}, foca no esforço/FC e "
            "capricha na hidratação. 💧"
        )

    @staticmethod
    def _pace_caution(feels: float) -> tuple[str, str]:
        """Quanto afrouxar o pace pelo calor (regra prática) + ressalva forte
        no calor extremo."""

        if feels >= 34:

            return "~20s/km+", " (no calor forte, o pace REAL cai — não cobre número)"

        if feels >= 31:

            return "~12-18s/km", ""

        return "~8-10s/km", ""
