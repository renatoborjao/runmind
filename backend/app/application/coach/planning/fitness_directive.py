"""Traduz a FORMA (o eixo "estou evoluindo?") numa DIRETRIZ pro coach (a
IA-treinadora) pesar ao montar o plano da semana. É o par da diretriz de corpo:
a de corpo diz 'o atleta está aguentando?' (carga × recuperação), esta diz 'o
atleta está MELHORANDO?' (evolução aeróbica ao longo das semanas).

O ponto do projeto: o plano é DINÂMICO — evoluiu, progride; estagnou, já traz o
estímulo que fura o platô; recuou, alivia. A decisão da dose é do coach (a IA),
nunca do atleta — a diretriz devolve o raciocínio pra ela decidir, não manda
perguntar. É MAIS UM insumo (soma ao histórico/execução/meta), ajuste GRADUAL —
nunca vira o plano de uma semana pra outra.

Puro/determinístico: recebe o FitnessEvolution já pronto (veredito triangulado)
e devolve texto; vazio quando não há sinal com lastro (o plano fica idêntico ao
de hoje). Ver [[project_ideias_produto]] e [[feedback_tudo_dinamico]]."""

from app.domain.entities.fitness_evolution import (
    EVO_DECLINING,
    EVO_IMPROVING,
    FitnessEvolution,
)

# cabeçalho comum: é MAIS UM insumo, o coach decide, e o ajuste é GRADUAL
_HEAD = (
    "FORMA (mais um insumo pra você, o COACH, pesar JUNTO do histórico, da "
    "execução real e da meta dele — NÃO é ordem nem pra perguntar ao atleta): "
)

_TAIL_GRADUAL = (
    " Ajuste GRADUAL e contínuo, ancorado no que ele vem executando — um "
    "degrau, não uma reforma; não vire o plano de cabeça pra baixo de uma "
    "semana pra outra."
)


def fitness_plan_directive(evo: FitnessEvolution) -> str:
    """Diretriz pro prompt do plano a partir do veredito de evolução. Vazio
    quando não há sinal com lastro (INSUFFICIENT) ou quando o dado é velho
    (parou de correr) — não empurra uma direção baseada em foto antiga."""

    if evo.stale or not evo.has_data:

        return ""

    period = _period(evo)

    corrob = _corroboration(evo)

    if evo.direction == EVO_IMPROVING:

        return (
            f"{_HEAD}a forma dele SUBIU {period}{corrob} — o corpo respondeu ao "
            "trabalho. Abre espaço pra evoluir a dose: um pouco mais de volume "
            "OU avançar/introduzir qualidade rumo à meta, conforme o momento "
            f"dele.{_TAIL_GRADUAL}"
        )

    if evo.direction == EVO_DECLINING:

        return (
            f"{_HEAD}a forma dele RECUOU {period}{corrob} — está custando mais "
            "pro mesmo rendimento. Evite SUBIR a intensidade agora: favoreça a "
            "base aeróbica e a recuperação até o sinal virar. Ajuste suave, sem "
            "cortar tudo à toa — é orientação, não alarme."
        )

    return (
        f"{_HEAD}a forma dele ESTAGNOU {period}{corrob} — a base está firme, "
        "mas parou de render. Pra ajudar a furar o platô, considere um estímulo "
        "de qualidade bem dosado (um tiro ou um limiar na semana), variando o "
        f"estímulo se já houver qualidade no plano.{_TAIL_GRADUAL}"
    )


def _period(evo: FitnessEvolution) -> str:

    weeks = evo.ef.weeks_covered if evo.ef is not None else 0

    return f"nas últimas ~{weeks} semanas" if weeks > 1 else "no período"


def _corroboration(evo: FitnessEvolution) -> str:
    """Cita os sinais que confirmam (economia em ritmo forte / VO₂máx /
    FC-repouso) — dá mais confiança à IA sem virar ordem."""

    parts = []

    if evo.quality is not None and evo.quality.direction != "STABLE":

        parts.append("economia em ritmo forte")

    if evo.vo2max is not None and evo.vo2max.direction != "STABLE":

        parts.append("VO₂máx da Garmin")

    if evo.rhr is not None and evo.rhr.direction != "STABLE":

        parts.append("FC de repouso")

    if not parts:

        return ""

    return f" (corroborado por {' e '.join(parts)})"
