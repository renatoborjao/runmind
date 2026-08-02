"""Cartão do SONO como eixo próprio — resposta ao "como está meu sono?". O sono
deixa de ser só uma etiqueta de 'limitador' na leitura do corpo e ganha leitura
própria: quanto, tendência, regularidade e dívida. Determinístico, sem IA.

Segue [[feedback_orientar_nao_mandar]]: aponta o custo com valor, sem cobrar —
sono nem sempre é controlável. O elo sono->PERFORMANCE com os números dele é o
coaching de sono (item #4, [[project_ideias_produto]]), construído por cima."""

from app.domain.entities.body_reading import FALLING, RISING
from app.domain.entities.sleep_impact import SleepImpact
from app.domain.entities.sleep_reading import (
    HEALTHY_FLOOR_HOURS,
    SleepReading,
)


class SleepReadingWriter:

    @staticmethod
    def write(
        reading: SleepReading,
        runner_name: str,
        impact: SleepImpact | None = None,
    ) -> str | None:
        """None quando não há noite medida (sem Garmin/sem sono) — o chamador
        cai no Gemini, que responde com naturalidade. `impact` (opcional) anexa
        o custo REAL do sono curto no desempenho dele, quando há sinal."""

        if not reading.has_data or reading.avg_hours is None:

            return None

        lines = [
            f"😴 Seu sono, {runner_name} (últimas 2 semanas)",
            "",
            f"• Média: {SleepReadingWriter._hours(reading.avg_hours)}/noite"
            f"{SleepReadingWriter._trend(reading.direction)}",
        ]

        if reading.consistency != "unknown":

            label = (
                "regular"
                if reading.consistency == "regular"
                else "irregular (varia bastante de uma noite pra outra)"
            )

            lines.append(f"• Regularidade: {label}")

        if reading.nights_counted:

            floor = int(HEALTHY_FLOOR_HOURS)

            lines.append(
                f"• Noites abaixo de {floor}h: "
                f"{reading.short_nights} de {reading.nights_counted}"
            )

        if reading.sleep_score is not None:

            lines.append(f"• Nota do Garmin: {reading.sleep_score}/100")

        if reading.deep_avg_hours is not None:

            lines.append(
                "• Sono profundo médio: "
                f"{SleepReadingWriter._hours(reading.deep_avg_hours)}"
            )

        lines.append("")

        # o CUSTO real (números dele) vem antes do fecho, quando há sinal
        if impact is not None and impact.has_finding:

            lines.append(SleepReadingWriter.impact_line(impact))

            lines.append("")

        lines.append(SleepReadingWriter._closing(reading))

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @staticmethod
    def impact_line(impact: SleepImpact) -> str:
        """A frase do custo: 'nos dias que dormiu <7h, teu pace no mesmo esforço
        caiu ~Xs/km'. Orienta com valor, não cobra ([[feedback_orientar_nao_mandar]])."""

        floor = int(impact.threshold_hours)

        when = (
            "depois das suas noites mais curtas (vs as mais longas)"
            if impact.relative
            else f"nos dias que você dormiu abaixo de {floor}h"
        )

        return (
            f"📉 Reparei uma coisa nos seus números: {when}, no MESMO esforço "
            f"seu pace ficou ~{impact.pace_cost_sec}s/km mais lento. O sono é o "
            "que mais segura sua evolução — quando der, é o ganho mais barato "
            "que existe."
        )

    @staticmethod
    def _closing(reading: SleepReading) -> str:
        """Fecho orientador — aponta o valor, não cobra."""

        if reading.debt:

            return (
                "Você vem dormindo abaixo do que o corpo pede pra treinar bem "
                f"(~{int(HEALTHY_FLOOR_HOURS)}h). Não é cobrança — sono é o "
                "ganho de evolução mais barato que existe; quando der, é onde "
                "mais rende. 💤"
            )

        if reading.direction == FALLING:

            return (
                "Seu sono vem caindo nas últimas semanas — fica de olho, é ele "
                "que sustenta a recuperação e os treinos."
            )

        if reading.direction == RISING:

            return "E vem melhorando — isso é combustível puro pros treinos. 👊"

        return "Tá dormindo bem — segue assim, é o que segura a evolução. 👊"

    @staticmethod
    def _hours(hours: float) -> str:
        """6.2 -> '6h12'."""

        whole = int(hours)

        minutes = round((hours - whole) * 60)

        if minutes == 60:

            whole += 1
            minutes = 0

        return f"{whole}h{minutes:02d}"

    @staticmethod
    def _trend(direction: str) -> str:

        if direction == RISING:

            return " ↗️ melhorando"

        if direction == FALLING:

            return " ↘️ caindo"

        return " → estável"
