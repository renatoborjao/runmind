"""Retrato ÚNICO "como você está" — o panorama que junta os eixos irmãos (corpo
& carga + forma) num raio-x só, coroado pela SÍNTESE cruzada.

Determinístico de ponta a ponta (sem IA, sem custo): o valor não está em narrar
bonito — pra isso existem as leituras avulsas (a do corpo é narrada pela IA no
on-demand; a evolução tem o seu writer detalhado) — está em CRUZAR os eixos num
único olhar. Aqui o retrato é crisp e consistente; a síntese vem do
[[StatePortraitSynthesizer]]. Degrada com elegância: mostra só os eixos com
lastro. None quando não há NADA pra dizer. Ver [[project_ideias_produto]] #21."""

from app.application.coach.intelligence.state_portrait_synthesizer import (
    StatePortraitSynthesizer,
)
from app.application.coach.writer.fitness_evolution_writer import (
    FitnessEvolutionWriter,
)
from app.application.coach.writer.health_snapshot_formatter import (
    HealthSnapshotFormatter,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_BUILDING,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
)
from app.domain.entities.fitness_evolution import (
    EVO_DECLINING,
    EVO_IMPROVING,
    EVO_STABLE,
    FitnessEvolution,
)

_BODY_ONELINER = {
    BODY_FRESH: "descansado, com espaço pra puxar",
    BODY_BALANCED: "carga e recuperação em equilíbrio",
    BODY_ABSORBING: "absorvendo bem o aumento de treino",
    BODY_RECOVERY_FLAG: "recuperação deu uma caída",
    BODY_STRAINED: "pedindo freio (carga alta, recuperação caindo)",
    BODY_BUILDING: "ainda juntando histórico de carga",
}

_LIMITER_SHORT = {
    "sono": "sono",
    "fc_repouso": "FC de repouso",
    "stress": "stress",
}


class StatePortraitWriter:

    @staticmethod
    def write(
        reading: BodyReading,
        evolution: FitnessEvolution,
        runner_name: str,
    ) -> str | None:
        """Retrato unificado. None quando NENHUM eixo tem leitura (o chamador
        decide o fallback / não envia)."""

        corpo_has = reading.recovery.has_data

        forma_has = evolution.has_data or evolution.stale

        if not corpo_has and not forma_has:

            return None

        state, conduct = StatePortraitSynthesizer.synthesize(reading, evolution)

        lines = [f"📷 Como você está, {runner_name}", "", state]

        corpo = StatePortraitWriter._corpo_section(reading)

        if corpo:

            lines.extend(["", *corpo])

        forma = StatePortraitWriter._forma_section(evolution)

        if forma:

            lines.extend(["", *forma])

        lines.extend(["", conduct])

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @staticmethod
    def _corpo_section(reading: BodyReading) -> list[str] | None:
        """Bloco do corpo & carga: um resumo em uma linha + o painel factual de
        recuperação (números do Garmin). Só quando há recuperação de verdade."""

        if not reading.recovery.has_data:

            return None

        oneliner = _BODY_ONELINER.get(
            reading.body_state, "seguimos acompanhando"
        )

        limiter = _LIMITER_SHORT.get(reading.limiter or "")

        if limiter:

            oneliner += f" · atenção ao {limiter}"

        out = [f"💪 Corpo: {oneliner}"]

        panel = HealthSnapshotFormatter.panel(reading.recovery)

        if panel:

            out.append(panel)

        return out

    @staticmethod
    def _forma_section(evolution: FitnessEvolution) -> list[str] | None:
        """Bloco da forma: direção em uma linha + a tradução sentível do EF.
        Honesto quando o dado é velho (sem leitura fresca)."""

        oneliner = StatePortraitWriter._forma_oneliner(evolution)

        if oneliner is None:

            return None

        out = [f"📈 Forma: {oneliner}"]

        # dado velho não ganha tradução tangível (seria número antigo)
        if not evolution.stale:

            tangible = FitnessEvolutionWriter.tangible(evolution)

            if tangible:

                out.append(f"   ↳ {tangible}")

        return out

    @staticmethod
    def _forma_oneliner(evolution: FitnessEvolution) -> str | None:

        if evolution.stale:

            days = evolution.days_since_last_run

            gap = f"faz {days} dias sem correr" if days else "faz um tempo sem correr"

            return f"sem leitura fresca ({gap})"

        if not evolution.has_data:

            return None

        return {
            EVO_IMPROVING: "subindo 📈",
            EVO_DECLINING: "recuou um pouco 📉",
            EVO_STABLE: "estável ➡️",
        }.get(evolution.direction, "estável ➡️")
