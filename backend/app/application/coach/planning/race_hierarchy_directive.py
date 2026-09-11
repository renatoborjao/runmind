"""HIERARQUIA de provas: quando o objetivo de FUNDO do atleta é mais longo do
que a próxima prova datada, essa prova é um CHECKPOINT (tune-up) no caminho — o
plano periodiza rumo ao alvo de fundo, tratando a prova próxima como marco (mira
a meta dela, mas sem taper agressivo nem reorganizar o macrociclo).

Diretriz do Renato (2026-09-10): "o plano tem que ser focado no 21k, mas também
pensando na prova de 15k e tentar fazer 1h15". O sistema já ANCORA a
periodização na prova mais próxima (correto pro curto prazo); esta diretriz dá
ao coach o FOCO no alvo de fundo, pra ele não tratar o checkpoint como fim.

MAIS UM insumo, não decreto — espelha o [[fitness_directive]] e o
[[race_projection_directive]]. Puro/determinístico. Ver
[[project_multiplos_objetivos]] e [[feedback_base_historico_sempre]]."""

from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.domain.entities.training_goal import TrainingGoal

# folga (km) pra considerar o fundo REALMENTE mais longo que a prova próxima —
# 21k vs 15k conta; 10k vs 10k (ou quase) não é hierarquia, é a mesma prova.
_LONGER_BY_KM = 2.0

_HEAD = (
    "HIERARQUIA DE PROVAS (mais um insumo pra você, o COACH — não decreto): "
)


def race_hierarchy_directive(
    goal: TrainingGoal | None,
    background_goal_text: str | None,
) -> str:
    """Diretriz de foco quando há um alvo de fundo mais longo que a prova
    próxima. Vazio quando não há prova datada, não há fundo mais longo, ou a
    prova próxima já É a distância de fundo (aí ela é o alvo, não checkpoint)."""

    if goal is None or goal.race_date is None:

        return ""

    background_km = BuildTrainingGoal._parse_distance(background_goal_text)

    if background_km is None or background_km <= goal.distance_km + _LONGER_BY_KM:

        return ""

    checkpoint = goal.race_label

    meta = f" (mira {goal.target_time})" if goal.target_time else ""

    bg = (
        "meia maratona"
        if abs(background_km - 21.0975) < 0.6
        else f"{background_km:.0f} km"
    )

    return (
        f"{_HEAD}o ALVO DE FUNDO do atleta é mais longo ({bg}) do que a próxima "
        f"prova ({checkpoint} em {goal.race_date.isoformat()}). Periodize "
        f"construindo endurance rumo ao alvo de {bg}; trate a prova de "
        f"{checkpoint} como CHECKPOINT/tune-up{meta} — prepare-o pra ir bem "
        "nela, mas SEM taper agressivo e sem reorganizar o macrociclo em torno "
        f"dela; ela serve à construção do alvo de {bg}. Depois dela, siga rumo "
        f"ao alvo de {bg} — não encerre o ciclo no checkpoint."
    )
