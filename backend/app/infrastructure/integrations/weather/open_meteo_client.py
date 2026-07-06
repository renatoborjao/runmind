import httpx

# Open-Meteo: previsão do tempo gratuita e SEM CHAVE (casa com a filosofia
# de ferramentas livres do RunMind). Só leitura, uso leve (1x/dia por atleta).
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


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
