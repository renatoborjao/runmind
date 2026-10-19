"""Linha de "se a prova fosse hoje" compartilhada entre o resumo semanal e
o recap mensal — mesma frase, um lugar só."""

from __future__ import annotations

from app.application.history.race_forecast import range_sentence
from app.application.planner.race_time_formatter import RaceTimeFormatter


class PredictedTimeLineFormatter:

    @staticmethod
    def line(
        predicted: dict | None,
        target_time: str | None,
    ) -> str | None:
        """None quando não há esforço-âncora confiável (silêncio, não
        invenção de número)."""

        if not predicted:

            return None

        forecast = predicted.get("range")

        if forecast:

            return PredictedTimeLineFormatter._range_line(forecast, target_time)

        line = f"🔮 Se a prova fosse hoje: ~{predicted['formatted']}"

        delta = predicted.get("delta_seconds")

        if delta is None or not target_time:

            return line

        if delta > 0:

            return (
                f"{line} — faltam ~{predicted['delta_formatted']} "
                f"pra bater a meta de {target_time}"
            )

        return (
            f"{line} — já bateria a meta de {target_time} com "
            f"~{predicted['delta_formatted']} de sobra"
        )

    @staticmethod
    def _range_line(forecast: dict, target_time: str | None) -> str:
        """Histórico e Garmin DISCORDAM: a previsão vira FAIXA rotulada, e a meta
        se posiciona dentro dela (nenhuma das duas fontes é "a verdade": o Garmin
        estima pelo VO₂máx e costuma ser otimista; o histórico só mostra o que o
        atleta já sustentou)."""

        line = f"🔮 Se a prova fosse hoje: {range_sentence(forecast)}"

        position = forecast.get("position")

        if not target_time or position is None:

            return line

        if position == "beaten":

            return (
                f"{line} — já bateria a meta de {target_time}, mesmo no "
                "cenário mais lento"
            )

        if position == "inside":

            return (
                f"{line} — a meta de {target_time} cabe nessa faixa; depende "
                "de manter a consistência nos treinos"
            )

        target_seconds = RaceTimeFormatter.parse_hms(target_time)

        gap = RaceTimeFormatter.format(forecast["low_seconds"] - (target_seconds or 0))

        return (
            f"{line} — faltam ~{gap} pra bater a meta de {target_time} "
            "mesmo no cenário mais rápido"
        )
