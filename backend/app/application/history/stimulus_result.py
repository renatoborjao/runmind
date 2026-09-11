"""Veredito de ESTÍMULO de um treino de tiro, a partir da comparação bloco-a-
bloco (prescrito × voltas rotuladas do Garmin). Fecha o limite da aderência de
estímulo: o pace MÉDIO não mede um intervalado (fica entre o forte e o trote) —
mas os BLOCOS medem. 'Executou os 5x1000 no ritmo?' vira sim/não com evidência.

Puro/determinístico: recebe o BlockComparison já pronto (montado no pós-treino,
com os dados completos do relógio) e devolve o resumo persistível. A captura e a
persistência ficam no pipeline; o report lê o resumo em lote (o arquivo reduzido
não guarda splits, então NÃO dá pra recalcular depois — por isso guarda-se o
veredito no momento certo). Ver [[planned_execution_matcher]] e
[[project_analise_treino_hibrida]]."""

from app.domain.entities.block_comparison import BlockComparison
from app.domain.entities.workout_step import INTERVAL

# vereditos do estímulo de tiro
STIMULUS_HIT = "HIT"        # executou os tiros no alvo
STIMULUS_PARTIAL = "PARTIAL"  # parte no alvo, parte fora/faltando
STIMULUS_MISS = "MISS"      # a maioria fora do alvo ou não feita

_HIT_RATIO = 0.7
_PARTIAL_RATIO = 0.4


def stimulus_result_from_comparison(
    comparison: BlockComparison | None,
) -> dict | None:
    """Resumo do estímulo dos TIROS: {on_target, total, verdict}. None quando
    o treino não tem bloco de tiro (nada estruturado a medir) ou os tiros não
    têm alvo de pace pra checar (aí a média já bastava)."""

    if comparison is None:

        return None

    intervals = [b for b in comparison.blocks if b.kind == INTERVAL]

    # tiros PRESCRITOS que nem apareceram nas voltas (o atleta parou a série)
    missed = [m for m in comparison.missing if m.lower().startswith("tiro")]

    total = len(intervals) + len(missed)

    if total == 0:

        return None  # não é treino de tiro

    checkable = [b for b in intervals if b.within_target is not None]

    if not checkable and not missed:

        return None  # tiros sem alvo de pace — a média já mede

    on_target = sum(1 for b in intervals if b.within_target is True)

    rate = on_target / total

    if rate >= _HIT_RATIO:

        verdict = STIMULUS_HIT

    elif rate >= _PARTIAL_RATIO:

        verdict = STIMULUS_PARTIAL

    else:

        verdict = STIMULUS_MISS

    return {"on_target": on_target, "total": total, "verdict": verdict}
