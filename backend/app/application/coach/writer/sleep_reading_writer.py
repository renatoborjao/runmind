"""Cartão do SONO como eixo próprio — resposta ao "como está meu sono?". O sono
deixa de ser só uma etiqueta de 'limitador' na leitura do corpo e ganha leitura
própria: quanto, tendência, regularidade e dívida. Determinístico, sem IA.

Segue [[feedback_orientar_nao_mandar]]: aponta o custo com valor, sem cobrar —
sono nem sempre é controlável. O elo sono->PERFORMANCE com os números dele é o
coaching de sono (item #4, [[project_ideias_produto]]), construído por cima."""

from app.application.history.sleep_performance_analyzer import (
    SLEEP_HURTS,
    SleepPerformanceReading,
)
from app.domain.entities.body_reading import FALLING, RISING
from app.domain.entities.sleep_reading import (
    HEALTHY_FLOOR_HOURS,
    SleepReading,
)


class SleepReadingWriter:

    @staticmethod
    def write(
        reading: SleepReading,
        runner_name: str,
        impact: SleepPerformanceReading | None = None,
    ) -> str | None:
        """None quando não há noite medida (sem Garmin/sem sono) — o chamador
        cai no Gemini, que responde com naturalidade. `impact` (opcional) anexa
        o CUSTO do sono curto na EXECUÇÃO dele, quando o histórico real mostra
        que pesa."""

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

        # o veredito real (números dele) vem antes do fecho, quando há lastro
        impact_line = SleepReadingWriter.impact_line(impact)

        if impact_line:

            lines.append(impact_line)

            lines.append("")

        lines.append(SleepReadingWriter._closing(reading))

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @staticmethod
    def impact_line(impact: SleepPerformanceReading | None) -> str:
        """O CUSTO do sono curto na execução DELE, em números dele: 'no mesmo
        esforço o pace ficou ~Xs/km mais lento'. Só quando o histórico real
        mostra que pesa — o 'não pesa' (SUSTAINS) fica com o coach, que não
        trava a dose por sono, mas o cartão não o exalta (nunca soar como aval
        a dormir pouco). Vazio sem lastro. Orienta com valor, não cobra
        ([[feedback_orientar_nao_mandar]])."""

        if impact is None or impact.direction != SLEEP_HURTS:

            return ""

        if impact.short_sleep_h is None or (impact.pace_delta_sec or 0) <= 0:

            return ""

        short = SleepReadingWriter._hours(impact.short_sleep_h)

        rested = SleepReadingWriter._hours(impact.rested_sleep_h or 0.0)

        return (
            "📉 Reparei uma coisa nos seus números: nas suas noites mais curtas "
            f"(~{short}, contra ~{rested} nas mais longas), no MESMO esforço "
            f"seu pace ficou ~{impact.pace_delta_sec}s/km mais lento. O sono é "
            "o que mais segura sua evolução — quando der, é o ganho mais "
            "barato que existe."
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
