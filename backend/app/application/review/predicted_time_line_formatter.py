"""Linha de "se a prova fosse hoje" compartilhada entre o resumo semanal e
o recap mensal — mesma frase, um lugar só."""

from __future__ import annotations


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
