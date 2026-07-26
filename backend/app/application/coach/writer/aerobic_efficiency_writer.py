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

                amount = AerobicEfficiencyWriter._amt(
                    fitness.pace_gain_sec, fitness.pace_gain_capped
                )

                return (
                    f"📈 Forma em alta: na mesma FC, {amount} "
                    f"s/km mais rápido que no início do período"
                )

            return "📈 Forma em alta: eficiência aeróbica subindo no período"

        if fitness.direction == EFF_DECLINING:

            return "📉 Eficiência aeróbica recuou um pouco no período"

        return "➡️ Forma estável: eficiência aeróbica mantida no período"

    # ------------------------------------------------------------------

    @staticmethod
    def _amt(n: int, capped: bool) -> str:
        """'~N' normalmente; 'mais de N' quando o valor bateu no teto de
        credibilidade (rampa de iniciante gera número real porém incrível)."""

        return f"mais de {n}" if capped else f"~{n}"

    @staticmethod
    def _gain_phrase(fitness: AerobicEfficiency) -> str | None:
        """A tradução tangível do ganho, quando os números têm tamanho de
        verdade (evita '0 bpm' / '0 s/km')."""

        parts = []

        if fitness.ref_pace and fitness.hr_drop_bpm and fitness.hr_drop_bpm > 0:

            pace = PaceFormatter.format(fitness.ref_pace)

            amount = AerobicEfficiencyWriter._amt(
                fitness.hr_drop_bpm, fitness.hr_drop_capped
            )

            parts.append(
                f"no mesmo pace (~{pace}/km), sua FC está {amount} "
                f"bpm mais baixa"
            )

        if fitness.ref_hr and fitness.pace_gain_sec and fitness.pace_gain_sec > 0:

            amount = AerobicEfficiencyWriter._amt(
                fitness.pace_gain_sec, fitness.pace_gain_capped
            )

            parts.append(
                f"na mesma FC (~{fitness.ref_hr} bpm), você corre "
                f"{amount} s/km mais rápido"
            )

        if not parts:

            return None

        return " — ou seja, ".join(parts)

    @staticmethod
    def _loss_phrase(fitness: AerobicEfficiency) -> str | None:

        if fitness.ref_pace and fitness.hr_drop_bpm and fitness.hr_drop_bpm < 0:

            pace = PaceFormatter.format(fitness.ref_pace)

            amount = AerobicEfficiencyWriter._amt(
                abs(fitness.hr_drop_bpm), fitness.hr_drop_capped
            )

            return (
                f"no mesmo pace (~{pace}/km), sua FC está {amount} bpm mais alta"
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
    def _anchor_phrase(fitness: AerobicEfficiency) -> str | None:
        """O ponto de referência tangível da janela: onde teu corpo está hoje
        na faixa aeróbica (pace × FC). Ancora o 'estável' num número sentível
        em vez de deixar só o conceito solto."""

        if not (fitness.ref_pace and fitness.ref_hr):

            return None

        pace = PaceFormatter.format(fitness.ref_pace)

        return (
            f"na faixa aeróbica, você tem rodado ~{pace}/km a ~{fitness.ref_hr} "
            f"bpm — e essa relação pace × FC ficou parada no período"
        )

    @staticmethod
    def _stable(fitness, name, period) -> str:

        lines = [
            f"➡️ Sua forma está estável, {name}.",
            "",
            f"Sua eficiência aeróbica se manteve {period}: você não perdeu "
            f"forma, mas também não ganhou — o corpo está rodando com o mesmo "
            f"custo de batimento de antes. Isso é a base se firmando, não é um "
            f"problema.",
        ]

        anchor = AerobicEfficiencyWriter._anchor_phrase(fitness)

        if anchor:

            runs = fitness.runs_counted

            base = f"Em números: {anchor}"

            if runs:

                base += f" (comparei {runs} corridas aeróbicas)"

            lines.append("")

            lines.append(base + ".")

        lines.append("")

        lines.append(
            "Pra furar o platô, o caminho é estímulo de qualidade bem dosado "
            "— um tiro ou um limiar na semana puxam o teto sem estourar a "
            "recuperação. É pra lá que teu próximo plano já vai apontar: eu "
            "ajusto a dose conforme a tua forma evolui. 👊"
        )

        return "\n".join(lines)
