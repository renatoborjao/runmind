"""Traduz a PROJEÇÃO DE PROVA do Garmin (5K/10K/meia/maratona) numa DIRETRIZ
pro coach pesar ao montar o plano — leitura de CAPACIDADE e de REALISMO da meta.

Diretriz do Renato (2026-09-10): é uma PROJEÇÃO (estimativa do relógio a partir
de VO₂máx+treino), MAIS UM dado pra o coach elaborar o plano e ler a evolução —
NÃO um decreto, nem número pra jogar ao atleta. Fica AO LADO do modelo de pace
real (VDOT do histórico, com a trava de condição), nunca por cima. Espelha o
[[fitness_directive]]: insumo, o coach decide, ajuste gradual.

Puro/determinístico: recebe a RacePrediction + a meta já prontas e devolve
texto; vazio quando não há projeção (device sem o dado). Ver
[[feedback_base_historico_sempre]] e [[feedback_tudo_dinamico]]."""

from app.domain.entities.race_prediction import RacePrediction
from app.domain.entities.training_goal import TrainingGoal

# distância padrão -> (tolerância km, atributo de segundos, atributo formatado)
_STD = [
    (5.0, 0.5, "time_5k_sec", "time_5k"),
    (10.0, 0.5, "time_10k_sec", "time_10k"),
    (21.0975, 0.6, "time_half_sec", "time_half"),
    (42.195, 0.5, "time_marathon_sec", "time_marathon"),
]

_HEAD = (
    "PROJEÇÃO DE PROVA (mais um insumo pra você, o COACH — o Garmin PROJETA o "
    "tempo a partir do VO₂máx e do treino; é ESTIMATIVA, não decreto nem número "
    "pra dizer ao atleta): "
)

_TAIL = (
    " Use como leitura de capacidade/realismo AO LADO do histórico e do modelo "
    "de pace real — NÃO prescreva ritmo de prova mais rápido do que a projeção "
    "sustenta hoje; ajuste GRADUAL."
)


def _parse_race_time(text: str | None) -> int | None:
    """'50:00'->3000s, '1:57:44'->7064s. None se vier torto/ausente."""

    if not text:

        return None

    try:

        parts = [int(p) for p in text.strip().split(":")]

    except (ValueError, AttributeError):

        return None

    if len(parts) == 3:

        h, m, s = parts

    elif len(parts) == 2:

        h, (m, s) = 0, parts

    else:

        return None

    return h * 3600 + m * 60 + s


def _gap_phrase(proj_sec: int, target_sec: int) -> str:
    """Compara a projeção com a meta e devolve a leitura pro coach."""

    diff = proj_sec - target_sec

    mins = abs(diff) // 60

    secs = abs(diff) % 60

    gap = f"~{mins}min{secs:02d}" if mins else f"~{secs}s"

    if diff <= 0:

        return (
            f"a projeção JÁ alcança a meta (folga de {gap}) — dá pra CONFIRMAR/"
            "afinar com qualidade específica da prova, sem inflar volume à toa"
        )

    if diff <= 90:

        return (
            f"falta {gap} pra meta — está PERTO; dá pra mirar com qualidade "
            "específica bem dosada (limiar/ritmo de prova), progressão gradual"
        )

    return (
        f"a meta ainda está {gap} à frente da projeção — periodize com "
        "paciência (base aeróbica + qualidade gradual); não force o ritmo de "
        "prova ainda"
    )


def race_projection_directive(
    prediction: RacePrediction | None,
    goal: TrainingGoal | None,
) -> str:
    """Diretriz pro prompt do plano a partir da projeção + meta. Vazio quando
    não há projeção com dado."""

    if prediction is None or not prediction.has_data:

        return ""

    # projeção pra a distância da META, quando ela casa uma prova padrão
    if goal is not None:

        for km, tol, sec_attr, str_attr in _STD:

            if abs(goal.distance_km - km) <= tol:

                proj_sec = getattr(prediction, sec_attr)

                proj_str = getattr(prediction, str_attr)

                if not proj_sec:

                    break

                target_sec = _parse_race_time(goal.target_time)

                if target_sec:

                    reading = _gap_phrase(proj_sec, target_sec)

                    return (
                        f"{_HEAD}pro alvo de {goal.race_label} o Garmin projeta "
                        f"~{proj_str} (meta {goal.target_time}): {reading}.{_TAIL}"
                    )

                return (
                    f"{_HEAD}pro alvo de {goal.race_label} o Garmin projeta "
                    f"~{proj_str}. Use como âncora de capacidade — o atleta não "
                    f"tem tempo-meta fixo, então mire evolução gradual.{_TAIL}"
                )

    # sem meta padrão casada: dá o retrato geral de capacidade (ainda é insumo)
    labels = [
        f"{name} ~{value}"
        for name, value in (
            ("5K", prediction.time_5k),
            ("10K", prediction.time_10k),
            ("21K", prediction.time_half),
            ("42K", prediction.time_marathon),
        )
        if value
    ]

    return (
        f"{_HEAD}capacidade projetada hoje — {' · '.join(labels)}. Leitura de "
        f"onde o motor está; dose a qualidade coerente com isso.{_TAIL}"
    )
