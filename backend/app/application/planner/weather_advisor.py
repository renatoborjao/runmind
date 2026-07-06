class WeatherAdvisor:
    """Transforma a previsão do dia numa linha curta e útil pro corredor —
    tempo + um conselho prático (calor/chuva/frio). Função pura, sem rede."""

    # limites pensados pro corredor brasileiro (calor é o risco mais comum)
    HOT_C = 30
    COLD_C = 12
    RAIN_LIKELY_PCT = 60

    @staticmethod
    def line(forecast: dict) -> str:

        temp = round(forecast["temp_max"])

        feels = round(forecast["feels_max"])

        rain = int(forecast["rain_prob"])

        # sensação só aparece quando destoa do termômetro
        feels_note = (
            f" (sensação {feels}°C)" if abs(feels - temp) >= 3 else ""
        )

        emoji, advice = WeatherAdvisor._advice(temp, feels, rain)

        return (
            f"{emoji} Clima hoje: máx {temp}°C{feels_note}, "
            f"{rain}% de chance de chuva. {advice}"
        )

    @staticmethod
    def _advice(temp: int, feels: int, rain: int) -> tuple[str, str]:

        hot = max(temp, feels)

        # calor primeiro (é o que mais atrapalha e tem risco)
        if hot >= WeatherAdvisor.HOT_C:

            return (
                "🥵",
                "Tá quente — corre no fresco (cedo ou fim de tarde) e "
                "capricha na hidratação 💧",
            )

        if rain >= WeatherAdvisor.RAIN_LIKELY_PCT:

            return (
                "🌧️",
                "Boa chance de chuva — se não curtir se molhar, rola "
                "trocar pela esteira.",
            )

        if temp <= WeatherAdvisor.COLD_C:

            return (
                "🥶",
                "Tá frio — aquece bem antes de acelerar e agasalha na "
                "saída 🧥",
            )

        return ("🌤️", "Condições boas pra treinar. Bora! 👟")
