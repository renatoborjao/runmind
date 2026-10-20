from datetime import date

import httpx

# Open-Meteo: previsão do tempo gratuita e SEM CHAVE (casa com a filosofia
# de ferramentas livres do Ritmind). Só leitura, uso leve (1x/dia por atleta).
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# geocodificação do mesmo provedor (cidade -> coordenada), também sem chave
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


class OpenMeteoClient:

    @staticmethod
    async def forecast_today(
        latitude: float,
        longitude: float,
    ) -> dict | None:
        """Resumo do tempo de HOJE na coordenada dada: temperatura máx/mín,
        sensação térmica máx e maior chance de chuva. `timezone=auto` resolve
        o "hoje" pelo fuso do próprio local. Indisponibilidade -> None (o
        lembrete sai sem a linha de clima, nunca quebra)."""

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "apparent_temperature_max,precipitation_probability_max"
            ),
            "timezone": "auto",
            "forecast_days": 1,
        }

        try:

            async with httpx.AsyncClient(timeout=8) as client:

                response = await client.get(FORECAST_URL, params=params)

            response.raise_for_status()

            daily = response.json().get("daily", {})

            return {
                "temp_max": daily["temperature_2m_max"][0],
                "temp_min": daily["temperature_2m_min"][0],
                "feels_max": daily["apparent_temperature_max"][0],
                "rain_prob": daily["precipitation_probability_max"][0],
            }

        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:

            print(f"Clima indisponível (Open-Meteo): {e}")

            return None

    @staticmethod
    async def geocode(city: str) -> tuple[float, float] | None:
        """Coordenada de uma cidade ("São Paulo/SP" -> só "São Paulo", no Brasil).
        Indisponível/não achou -> None (o ajuste de calor da prova simplesmente não
        sai, nunca quebra)."""

        name = (city or "").split("/")[0].strip()

        if not name:

            return None

        params = {"name": name, "count": 1, "language": "pt", "countryCode": "BR"}

        try:

            async with httpx.AsyncClient(timeout=8) as client:

                response = await client.get(GEOCODING_URL, params=params)

            response.raise_for_status()

            first = (response.json().get("results") or [])[0]

            return float(first["latitude"]), float(first["longitude"])

        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as e:

            print(f"Geocodificação indisponível (Open-Meteo) p/ '{name}': {e}")

            return None

    @staticmethod
    async def forecast_on(
        latitude: float,
        longitude: float,
        day: date,
        start_hour: int = 7,
        hours: int = 2,
    ) -> dict | None:
        """O tempo de UM DIA futuro (até ~16 dias à frente) na janela em que o atleta
        estará correndo: média de temperatura, sensação térmica e umidade das `hours`
        horas a partir de `start_hour` (hora local do lugar). Sem previsão publicada
        pra esse dia -> None."""

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m",
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "timezone": "auto",
        }

        try:

            async with httpx.AsyncClient(timeout=8) as client:

                response = await client.get(FORECAST_URL, params=params)

            response.raise_for_status()

            hourly = response.json()["hourly"]

            wanted = range(start_hour, start_hour + max(1, hours))

            rows = [
                (temp, feels, humidity)
                for stamp, temp, feels, humidity in zip(
                    hourly["time"],
                    hourly["temperature_2m"],
                    hourly["apparent_temperature"],
                    hourly["relative_humidity_2m"],
                )
                if int(stamp[11:13]) in wanted
                and temp is not None
                and feels is not None
            ]

            if not rows:

                return None

            count = len(rows)

            humidities = [h for _, _, h in rows if h is not None]

            return {
                "temp": sum(r[0] for r in rows) / count,
                "feels": sum(r[1] for r in rows) / count,
                "humidity": sum(humidities) / len(humidities) if humidities else None,
            }

        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as e:

            print(f"Previsão do dia da prova indisponível (Open-Meteo): {e}")

            return None
