"""Narra o veredito COMBINADO do "estou evoluindo?" (EF + VO₂máx + FC-repouso +
arco longo) numa mensagem athlete-facing. Determinístico — o veredito e os
números vêm prontos do analisador, então não há custo nem risco de IA.

O canal envia texto puro (sem negrito), então a formatação é por HIERARQUIA
VISUAL: título, resumo curto, um painel de sinais com emoji por linha (estilo da
casa, igual [[HealthSnapshotFormatter]]) e um fecho de rumo. Mostra CADA sinal
que teve lastro e o que ainda está juntando histórico. Ver [[FitnessEvolution]]."""

from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    AerobicEfficiency,
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

        # dado velho: faz tempo demais sem correr — não damos veredito de
        # "agora" como se fosse fresco. Isto vem ANTES do has_data: mesmo com
        # sinal antigo com lastro, a leitura honesta é "sem leitura fresca".
        if evo.stale:

            return FitnessEvolutionWriter._stale(evo, runner_name)

        if not evo.has_data:

            return None

        lines = [FitnessEvolutionWriter._headline(evo, runner_name), ""]

        lines.append(FitnessEvolutionWriter._summary(evo))

        lines.append("")

        lines.append("📊 O que dá pra medir:")

        lines.extend(FitnessEvolutionWriter._signal_lines(evo))

        lines.append("")

        lines.append(FitnessEvolutionWriter._closer(evo))

        return "\n".join(lines)

    @staticmethod
    def line(evo: FitnessEvolution) -> str | None:
        """Uma linha compacta pro recap mensal. Delega ao EF (o sinal
        sempre-presente e tangível)."""

        # dado velho: sem corrida recente, a linha de forma seria enganosa —
        # cala (o recap simplesmente omite a linha de evolução).
        if evo.stale:

            return None

        if evo.ef is None:

            return None

        from app.application.coach.writer.aerobic_efficiency_writer import (
            AerobicEfficiencyWriter,
        )

        return AerobicEfficiencyWriter.line(evo.ef)

    @staticmethod
    def tangible(evo: FitnessEvolution) -> str | None:
        """A tradução sentível do EF numa linha (no mesmo esforço, quanto mais
        rápido / na mesma FC). Pública pra o retrato unificado reusar sem
        duplicar a regra. None quando não há EF com tamanho."""

        if evo.ef is None:

            return None

        return FitnessEvolutionWriter._ef_tangible(evo.ef)

    # ------------------------------------------------------------------

    @staticmethod
    def _stale(evo: FitnessEvolution, name: str) -> str:
        """Sem corrida recente: honesto é dizer que a leitura é de um momento
        passado, não dar um veredito velho como se fosse de agora."""

        days = evo.days_since_last_run

        gap = f"faz {days} dias" if days else "faz um tempo"

        return "\n".join(
            [
                f"😴 Ainda sem leitura fresca da tua evolução, {name}.",
                "",
                f"{gap.capitalize()} que não registro uma corrida sua — então o "
                "que eu tenho reflete aquele momento, não o de agora. Prefiro "
                "não te dar um veredito velho como se fosse atual.",
                "",
                "🎯 Quando você voltar a rodar, em poucas corridas eu já releio "
                "tua forma com dado fresco. 👊",
            ]
        )

    @staticmethod
    def _headline(evo: FitnessEvolution, name: str) -> str:

        if evo.direction == EVO_IMPROVING:

            return f"📈 Você está evoluindo, {name}!"

        if evo.direction == EVO_DECLINING:

            return f"📉 Vale ficar de olho na forma, {name}."

        return f"➡️ Sua forma está estável, {name}."

    @staticmethod
    def _summary(evo: FitnessEvolution) -> str:
        """Uma frase — o veredito em linguagem simples."""

        mixed = (
            " (os sinais não apontam todos pro mesmo lado, então vem com um pé "
            "atrás)"
            if evo.confidence == EVO_MIXED
            else ""
        )

        if evo.direction == EVO_IMPROVING:

            return f"Teu corpo está rendendo mais pelo mesmo esforço.{mixed}"

        if evo.direction == EVO_DECLINING:

            return (
                "Está custando mais pro mesmo rendimento — costuma ser fadiga, "
                f"calor ou fase puxada. Não é susto, é sinal pra observar.{mixed}"
            )

        return (
            "Você não perdeu forma, mas também não deu um salto: o corpo rende "
            f"com o mesmo custo de antes. É a base se firmando.{mixed}"
        )

    @staticmethod
    def _signal_lines(evo: FitnessEvolution) -> list[str]:
        """Um bloco por sinal com lastro (emoji + rótulo), a economia com sua
        tradução tangível numa sublinha indentada; fecha com o que falta."""

        out = []

        if evo.ef is not None:

            out.append(
                f"• ⚙️ Economia aeróbica: "
                f"{FitnessEvolutionWriter._ef_word(evo.ef)}"
            )

            tangible = FitnessEvolutionWriter._ef_tangible(evo.ef)

            if tangible:

                out.append(f"   ↳ {tangible}")

        if evo.ef_long is not None:

            out.append(
                f"• 📈 No arco longo (~{evo.ef_long.span_weeks} sem): "
                f"{FitnessEvolutionWriter._word(evo.ef_long)}"
            )

        if evo.quality is not None:

            out.append(
                f"• 🔥 Em ritmo forte (limiar/tiro): "
                f"{FitnessEvolutionWriter._word(evo.quality)}"
            )

        if evo.vo2max is not None:

            out.append(
                f"• 🫁 VO₂máx (Garmin): "
                f"{FitnessEvolutionWriter._word(evo.vo2max)} "
                f"({FitnessEvolutionWriter._range(evo.vo2max, 1)})"
            )

        if evo.rhr is not None:

            out.append(
                f"• 💓 FC de repouso: "
                f"{FitnessEvolutionWriter._rhr_word(evo.rhr)} "
                f"({FitnessEvolutionWriter._range(evo.rhr, 0)} bpm)"
            )

        pending = FitnessEvolutionWriter._pending(evo)

        if pending:

            out.append(pending)

        return out

    @staticmethod
    def _ef_tangible(ef: AerobicEfficiency) -> str | None:
        """A tradução sentível do EF numa linha curta (a mais intuitiva: no
        mesmo esforço, quanto mais rápido); só quando o número tem tamanho."""

        if ef.ref_hr and ef.pace_gain_sec and ef.pace_gain_sec > 0:

            amount = (
                f"mais de {ef.pace_gain_sec}"
                if ef.pace_gain_capped
                else f"~{ef.pace_gain_sec}"
            )

            return (
                f"na mesma FC (~{ef.ref_hr} bpm), {amount} s/km mais "
                "rápido que no começo"
            )

        if ef.ref_pace and ef.hr_drop_bpm and ef.hr_drop_bpm < 0:

            pace = PaceFormatter.format(ef.ref_pace)

            amount = (
                f"mais de {abs(ef.hr_drop_bpm)}"
                if ef.hr_drop_capped
                else f"~{abs(ef.hr_drop_bpm)}"
            )

            return (
                f"no mesmo pace (~{pace}/km), FC {amount} bpm mais "
                "alta que no começo"
            )

        return None

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

        return "• ⏳ " + " e ".join(missing) + ": ainda juntando histórico"

    @staticmethod
    def _closer(evo: FitnessEvolution) -> str:

        if evo.direction == EVO_DECLINING:

            return (
                "🎯 Teu próximo plano já leva isso em conta: aliviar e priorizar "
                "a recuperação até o sinal virar. 👊"
            )

        if evo.direction == EVO_IMPROVING:

            return (
                "🎯 Teu próximo plano já aproveita a janela: progrido a dose com "
                "o corpo respondendo — sempre gradual. 👊"
            )

        return (
            "🎯 Pra sair do platô, o caminho é qualidade bem dosada (tiro/"
            "limiar) — é pra lá que teu próximo plano já aponta. 👊"
        )

    # -- vocabulário por sinal ----------------------------------------

    @staticmethod
    def _ef_word(ef: AerobicEfficiency) -> str:

        if ef.direction == EFF_IMPROVING:

            return "subindo 📈"

        if ef.direction == EFF_DECLINING:

            return "recuou um pouco 📉"

        return "estável ➡️"

    @staticmethod
    def _word(trend: SignalTrend) -> str:

        if trend.direction == TREND_IMPROVING:

            return "subindo 📈"

        if trend.direction == TREND_DECLINING:

            return "caindo 📉"

        return "estável ➡️"

    @staticmethod
    def _rhr_word(trend: SignalTrend) -> str:
        """FC de repouso: cair é bom (a tendência já vem orientada)."""

        if trend.direction == TREND_IMPROVING:

            return "caindo, bom sinal 📈"

        if trend.direction == TREND_DECLINING:

            return "subindo, atenção 📉"

        return "estável ➡️"

    @staticmethod
    def _range(trend: SignalTrend, decimals: int) -> str:
        """'de X pra Y' com os extremos ajustados pela reta."""

        a = round(trend.earlier_value, decimals)

        b = round(trend.recent_value, decimals)

        if decimals == 0:

            a, b = int(a), int(b)

        return f"de {a} pra {b}"
