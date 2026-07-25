"""Traduz a FORMA aeróbica (o eixo "estou evoluindo?") numa DIRETRIZ pro coach
(a IA-treinadora) pesar ao montar o plano da semana. É o par da diretriz de
corpo: a de corpo diz 'o atleta está aguentando?' (carga × recuperação), esta
diz 'o atleta está MELHORANDO?' (eficiência aeróbica ao longo das semanas).

O ponto do projeto: o plano é DINÂMICO — quando o atleta evolui, o plano
progride sozinho; quando estagna, o plano já traz o estímulo que fura o platô;
quando recua, o plano alivia. A decisão da dose é do coach (a IA), nunca do
atleta — a diretriz devolve o raciocínio pra ela decidir, não manda perguntar.

Puro/determinístico: recebe a AerobicEfficiency já pronta e devolve texto;
string vazia quando não há corridas comparáveis suficientes (o plano fica
idêntico ao de hoje). Ver [[project_ideias_produto]] e [[feedback_tudo_dinamico]]."""

from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    AerobicEfficiency,
)


def fitness_plan_directive(fitness: AerobicEfficiency) -> str:
    """Diretriz pro prompt do plano a partir da tendência de eficiência
    aeróbica. Vazio quando não há dado comparável (INSUFFICIENT)."""

    if not fitness.has_data:

        return ""

    weeks = fitness.weeks_covered

    period = f"nas últimas ~{weeks} semanas" if weeks > 1 else "no período"

    # cabeçalho comum: é MAIS UM insumo (soma ao histórico/execução/meta), o
    # coach decide, e o ajuste é GRADUAL — nunca vira o plano de uma semana
    # pra outra. Fecha a porta pro exagero.
    head = (
        "FORMA AERÓBICA (mais um insumo pra você, o COACH, pesar JUNTO do "
        "histórico, da execução real e da meta dele — NÃO é ordem nem pra "
        "perguntar ao atleta): "
    )

    tail_gradual = (
        " Ajuste GRADUAL e contínuo, ancorado no que ele vem executando — um "
        "degrau, não uma reforma; não vire o plano de cabeça pra baixo de uma "
        "semana pra outra."
    )

    if fitness.direction == EFF_IMPROVING:

        return (
            f"{head}a eficiência aeróbica dele SUBIU {period} — o corpo "
            "respondeu ao trabalho, está correndo mais rápido pra cada "
            "batimento. Abre espaço pra evoluir a dose: um pouco mais de "
            "volume OU avançar/introduzir qualidade rumo à meta, conforme o "
            f"momento dele.{tail_gradual}"
        )

    if fitness.direction == EFF_DECLINING:

        return (
            f"{head}a eficiência aeróbica dele RECUOU {period} — está custando "
            "mais batimento pro mesmo ritmo. Evite SUBIR a intensidade agora: "
            "favoreça a base aeróbica e a recuperação até o sinal virar. "
            "Ajuste suave, sem cortar tudo à toa — é orientação, não alarme."
        )

    return (
        f"{head}a eficiência aeróbica dele ESTAGNOU {period} — a base está "
        "firme, mas parou de render. Pra ajudar a furar o platô, considere um "
        "estímulo de qualidade bem dosado (um tiro ou um limiar na semana), "
        f"variando o estímulo se já houver qualidade no plano.{tail_gradual}"
    )
