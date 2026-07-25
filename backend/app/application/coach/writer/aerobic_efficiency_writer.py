"""Narra a eficiência aeróbica (o eixo "estou evoluindo?") numa mensagem
athlete-facing. Determinístico e factual — o veredito e os números já vêm
prontos do analisador, então não precisa de IA (grátis, e não há o que a IA
'resuma' e desconfigure). Ver [[project_ideias_produto]]."""

from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    AerobicEfficiency,
)


class AerobicEfficiencyWriter:

    @staticmethod
    def write(fitness: AerobicEfficiency, runner_name: str) -> str | None:
        """Mensagem da tendência de forma. None quando não há corridas
        comparáveis suficientes (o chamador decide o fallback)."""

        if not fitness.has_data:

            return None

        weeks = fitness.weeks_covered

        period = f"nas últimas ~{weeks} semanas" if weeks > 1 else "no período"

        if fitness.direction == EFF_IMPROVING:

            return AerobicEfficiencyWriter._improving(fitness, runner_name, period)

        if fitness.direction == EFF_DECLINING:

            return AerobicEfficiencyWriter._declining(fitness, runner_name, period)

        return AerobicEfficiencyWriter._stable(fitness, runner_name, period)

    @staticmethod
    def line(fitness: AerobicEfficiency) -> str | None:
        """Versão compacta de UMA linha, pra entrar como bullet no recap
        mensal ao lado dos outros números. None sem dado comparável."""

        if not fitness.has_data:

            return None

        if fitness.direction == EFF_IMPROVING:

            if fitness.ref_hr and fitness.pace_gain_sec and fitness.pace_gain_sec > 0:

                return (
                    f"📈 Forma em alta: na mesma FC, ~{fitness.pace_gain_sec} "
                    f"s/km mais rápido que no início do período"
                )

            return "📈 Forma em alta: eficiência aeróbica subindo no período"

        if fitness.direction == EFF_DECLINING:

            return "📉 Eficiência aeróbica recuou um pouco no período"

        return "➡️ Forma estável: eficiência aeróbica mantida no período"

    # ------------------------------------------------------------------

    @staticmethod
    def _gain_phrase(fitness: AerobicEfficiency) -> str | None:
        """A tradução tangível do ganho, quando os números têm tamanho de
        verdade (evita '0 bpm' / '0 s/km')."""

        parts = []

        if fitness.ref_pace and fitness.hr_drop_bpm and fitness.hr_drop_bpm > 0:

            pace = PaceFormatter.format(fitness.ref_pace)

            parts.append(
                f"no mesmo pace (~{pace}/km), sua FC está ~{fitness.hr_drop_bpm} "
                f"bpm mais baixa"
            )

        if fitness.ref_hr and fitness.pace_gain_sec and fitness.pace_gain_sec > 0:

            parts.append(
                f"na mesma FC (~{fitness.ref_hr} bpm), você corre "
                f"~{fitness.pace_gain_sec} s/km mais rápido"
            )

        if not parts:

            return None

        return " — ou seja, ".join(parts)

    @staticmethod
    def _loss_phrase(fitness: AerobicEfficiency) -> str | None:

        if fitness.ref_pace and fitness.hr_drop_bpm and fitness.hr_drop_bpm < 0:

            pace = PaceFormatter.format(fitness.ref_pace)

            return (
                f"no mesmo pace (~{pace}/km), sua FC está ~"
                f"{abs(fitness.hr_drop_bpm)} bpm mais alta"
            )

        return None

    @staticmethod
    def _improving(fitness, name, period) -> str:

        lines = [
            f"📈 Sua forma está evoluindo, {name}!",
            "",
            f"Sua eficiência aeróbica subiu {period}: o corpo ficou mais "
            f"econômico, correndo mais rápido pra cada batimento.",
        ]

        gain = AerobicEfficiencyWriter._gain_phrase(fitness)

        if gain:

            lines.append("")

            lines.append(f"Em números: {gain}.")

        lines.append("")

        lines.append(
            "É a base aeróbica rendendo — exatamente o que sustenta a evolução "
            "rumo à sua meta. 👊"
        )

        return "\n".join(lines)

    @staticmethod
    def _declining(fitness, name, period) -> str:

        lines = [
            f"📉 Fique de olho na forma, {name}.",
            "",
            f"Sua eficiência aeróbica recuou um pouco {period}: está custando "
            f"mais batimento pro mesmo ritmo.",
        ]

        loss = AerobicEfficiencyWriter._loss_phrase(fitness)

        if loss:

            lines.append("")

            lines.append(f"Em números: {loss}.")

        lines.append("")

        lines.append(
            "Costuma ser calor, fadiga acumulada ou uma fase mais puxada — "
            "vale caprichar no sono e na recuperação. Não é motivo pra susto, "
            "é um sinal pra observar."
        )

        return "\n".join(lines)

    @staticmethod
    def _stable(fitness, name, period) -> str:

        return (
            f"➡️ Forma estável, {name}. Sua eficiência aeróbica se manteve "
            f"{period} — sem ganho nem perda claros. A consistência segura a "
            f"base; pra destravar mais evolução, um estímulo de qualidade "
            f"(tiro/limiar) bem dosado ajuda."
        )
