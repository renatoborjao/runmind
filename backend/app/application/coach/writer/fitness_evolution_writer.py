"""Narra o veredito COMBINADO do "estou evoluindo?" (EF + VO₂máx + FC-repouso +
arco longo) numa mensagem athlete-facing. Determinístico — o veredito e os
números vêm prontos do analisador, então não há custo nem risco de IA.

Reaproveita as traduções tangíveis do EF ([[AerobicEfficiencyWriter]]) e mostra
CADA sinal que teve lastro, deixando claro por que a leitura é o que é — e o que
ainda está juntando histórico pra entrar na conta. Ver [[FitnessEvolution]]."""

from app.application.coach.writer.aerobic_efficiency_writer import (
    AerobicEfficiencyWriter,
)
from app.domain.entities.fitness_evolution import (
    EVO_DECLINING,
    EVO_IMPROVING,
    EVO_MIXED,
    FitnessEvolution,
)
from app.domain.entities.signal_trend import (
    TREND_DECLINING,
    TREND_IMPROVING,
    SignalTrend,
)


class FitnessEvolutionWriter:

    @staticmethod
    def write(evo: FitnessEvolution, runner_name: str) -> str | None:
        """Mensagem completa da evolução. None quando não há NENHUM sinal com
        lastro (o chamador decide o fallback)."""

        if not evo.has_data:

            return None

        lines = [FitnessEvolutionWriter._headline(evo, runner_name)]

        lines.append("")

        lines.append(FitnessEvolutionWriter._explanation(evo))

        why = FitnessEvolutionWriter._signal_lines(evo)

        if why:

            lines.append("")

            lines.append("Por que essa leitura:")

            lines.extend(why)

        lines.append("")

        lines.append(FitnessEvolutionWriter._closer(evo))

        return "\n".join(lines)

    @staticmethod
    def line(evo: FitnessEvolution) -> str | None:
        """Uma linha compacta pro recap mensal. Delega ao EF (o sinal
        sempre-presente e tangível)."""

        if evo.ef is None:

            return None

        return AerobicEfficiencyWriter.line(evo.ef)

    # ------------------------------------------------------------------

    @staticmethod
    def _headline(evo: FitnessEvolution, name: str) -> str:

        if evo.direction == EVO_IMPROVING:

            return f"📈 Você está evoluindo, {name}!"

        if evo.direction == EVO_DECLINING:

            return f"📉 Vale ficar de olho na forma, {name}."

        return f"➡️ Sua forma está estável, {name}."

    @staticmethod
    def _explanation(evo: FitnessEvolution) -> str:

        mixed = (
            " Os sinais não apontam todos pro mesmo lado — por isso a leitura "
            "vem com um pé atrás."
            if evo.confidence == EVO_MIXED
            else ""
        )

        if evo.direction == EVO_IMPROVING:

            return (
                "O conjunto do que dá pra medir aponta pra cima: teu corpo está "
                "rendendo mais pelo mesmo esforço." + mixed
            )

        if evo.direction == EVO_DECLINING:

            return (
                "O conjunto do que dá pra medir recuou um pouco — está custando "
                "mais pro mesmo rendimento. Costuma ser fadiga acumulada, calor "
                "ou fase puxada; não é motivo pra susto, é sinal pra observar."
                + mixed
            )

        return (
            "Você não perdeu forma, mas também não deu um salto no período: o "
            "corpo está rendendo com o mesmo custo de antes. É a base se "
            "firmando, não é um problema." + mixed
        )

    @staticmethod
    def _signal_lines(evo: FitnessEvolution) -> list[str]:
        """Um bullet por sinal que teve lastro + o que ainda falta juntar."""

        out = []

        if evo.ef is not None:

            out.append(f"• {FitnessEvolutionWriter._ef_line(evo.ef)}")

        if evo.ef_long is not None:

            out.append(
                f"• No arco longo (~{evo.ef_long.span_weeks} semanas): economia "
                f"aeróbica {FitnessEvolutionWriter._word(evo.ef_long)}"
            )

        if evo.vo2max is not None:

            out.append(
                f"• VO₂máx (Garmin): {FitnessEvolutionWriter._word(evo.vo2max)} "
                f"({FitnessEvolutionWriter._range(evo.vo2max, 1)})"
            )

        if evo.rhr is not None:

            out.append(
                f"• FC de repouso: {FitnessEvolutionWriter._rhr_word(evo.rhr)} "
                f"({FitnessEvolutionWriter._range(evo.rhr, 0)} bpm)"
            )

        pending = FitnessEvolutionWriter._pending(evo)

        if pending:

            out.append(pending)

        return out

    @staticmethod
    def _ef_line(ef) -> str:
        """A economia aeróbica curta + tradução tangível, quando há."""

        gain = AerobicEfficiencyWriter._gain_phrase(ef)

        loss = AerobicEfficiencyWriter._loss_phrase(ef)

        detail = gain or loss

        base = f"Eficiência aeróbica (velocidade/FC): {FitnessEvolutionWriter._ef_word(ef)}"

        return f"{base} — {detail}" if detail else base

    @staticmethod
    def _pending(evo: FitnessEvolution) -> str | None:
        """Deixa claro (uma vez) o que ainda está juntando histórico — responde
        'por que só o EF conta hoje?' sem virar ruído."""

        missing = []

        if evo.vo2max is None:

            missing.append("VO₂máx")

        if evo.rhr is None:

            missing.append("FC de repouso")

        if not missing:

            return None

        return (
            "• (" + " e ".join(missing) + " ainda juntando histórico pra "
            "entrar nessa conta)"
        )

    @staticmethod
    def _closer(evo: FitnessEvolution) -> str:

        if evo.direction == EVO_DECLINING:

            return (
                "Teu próximo plano já leva isso em conta: aliviar e priorizar a "
                "recuperação até o sinal virar. 👊"
            )

        if evo.direction == EVO_IMPROVING:

            return (
                "Teu próximo plano já aproveita a janela: progride a dose com o "
                "corpo respondendo — sempre gradual, ancorado no teu histórico. 👊"
            )

        return (
            "Pra sair do platô, o caminho é estímulo de qualidade bem dosado "
            "(tiro/limiar). É pra lá que teu próximo plano já aponta — ajusto a "
            "dose conforme a tua forma evolui. 👊"
        )

    # -- vocabulário por sinal ----------------------------------------

    @staticmethod
    def _ef_word(ef) -> str:

        from app.domain.entities.aerobic_efficiency import (
            EFF_DECLINING,
            EFF_IMPROVING,
        )

        if ef.direction == EFF_IMPROVING:

            return "subindo"

        if ef.direction == EFF_DECLINING:

            return "recuou um pouco"

        return "estável"

    @staticmethod
    def _word(trend: SignalTrend) -> str:

        if trend.direction == TREND_IMPROVING:

            return "subindo"

        if trend.direction == TREND_DECLINING:

            return "caindo"

        return "estável"

    @staticmethod
    def _rhr_word(trend: SignalTrend) -> str:
        """FC de repouso: cair é bom (a tendência já vem orientada)."""

        if trend.direction == TREND_IMPROVING:

            return "caindo (bom sinal)"

        if trend.direction == TREND_DECLINING:

            return "subindo (atenção)"

        return "estável"

    @staticmethod
    def _range(trend: SignalTrend, decimals: int) -> str:
        """'de X pra Y' com os extremos ajustados pela reta."""

        a = round(trend.earlier_value, decimals)

        b = round(trend.recent_value, decimals)

        if decimals == 0:

            a, b = int(a), int(b)

        return f"de {a} pra {b}"
