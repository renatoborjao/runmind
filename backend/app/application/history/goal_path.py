"""ROTA ATÉ A META — a conta que faltava ao coach: onde o atleta PRECISA estar até o dia da
prova × pra onde o plano atual o leva.

O coach via tudo (forma estagnada, 0% de esforço forte, o atleta dizendo que os treinos estão
leves) e mesmo assim dava o menor passo: cada semana um degrau em cima da anterior, ancorada no
que ele cumpriu — uma catraca que nunca sai do lugar (Leonardo, 21/10: 10 km em 1h em 8 semanas,
longão parado em ~9 km, 0 minuto em ritmo de prova). Nada no coach comparava o caminho com o que
a meta exige. O mapa até a prova mostra as fases; esta conta mostra os NÚMEROS e a diferença.

É CONHECIMENTO + DADO pra IA, nunca decreto ([[feedback_ia_decide_sem_regras]]): a referência é
o que um amador que corre pra bater um TEMPO costuma ter feito até a semana da prova (hipótese de
treinador, em faixa), e a projeção é só "se seguir no passo das últimas semanas". O coach decide
como fechar a diferença — ou diz ao atleta que não cabe com segurança e propõe ajustar a meta.
Puro/determinístico."""

from dataclasses import dataclass
from statistics import mean

# distância (km) até a qual vale a faixa → (longão no pico, volume semanal no pico), em km.
# Amador correndo pra bater um tempo; com ≤ 3 corridas por semana mire no PISO do volume.
_REFERENCE = (
    (5.5, (8, 10), (20, 30)),
    (10.5, (11, 13), (28, 38)),
    (16.0, (15, 18), (35, 45)),
    (22.0, (18, 21), (40, 55)),
    (99.0, (30, 35), (55, 75)),
)

# a prova mais perto que isto está no taper: não há mais "rota", o recuo é quem manda
_MIN_WEEKS_LEFT = 3

# semanas fechadas olhadas (4 recentes × 4 anteriores) e o piso pra falar de tendência
_WINDOW = 4

# abaixo disto a diferença é ruído, não vale a frase
_MIN_GAP_KM = 1.0

# o passo recente não vira promessa: a projeção nunca passa de ~15% acima da MELHOR semana / do
# MAIOR treino que ele já fez (uma tendência de 4 semanas extrapolada por 8 dava 69 km/semana)
_PROJECTION_CAP = 1.15


@dataclass(slots=True)
class GoalPath:

    weeks_left: int
    distance_km: float
    target_time: str | None
    long_ref: tuple[int, int]
    week_ref: tuple[int, int]
    recent_long: float
    best_long: float
    recent_week: float
    best_week: float
    projected_long: float
    projected_week: float
    long_gap: float
    week_gap: float
    runs_per_week: int
    hard_pct: int | None


def reference_for(distance_km: float) -> tuple[tuple[int, int], tuple[int, int]]:
    """(faixa do longão, faixa do volume semanal) no pico de preparo pra essa distância."""

    for limit, long_run, weekly in _REFERENCE:

        if distance_km <= limit:

            return long_run, weekly

    return _REFERENCE[-1][1], _REFERENCE[-1][2]


def _running_mean(values: list[float]) -> float | None:

    ran = [v for v in values if v > 0]

    return mean(ran) if ran else None


def assess(
    *,
    distance_km: float | None,
    target_time: str | None,
    weeks_left: int | None,
    weekly_km: list[float],
    longest_km: list[float],
    runs_per_week: int = 3,
    hard_pct: int | None = None,
) -> GoalPath | None:
    """A rota até a meta. `weekly_km`/`longest_km`: as últimas 8 semanas FECHADAS (da mais antiga
    pra mais recente; semana sem corrida = 0). None sem distância, sem data de prova, com a prova
    no taper ou sem corrida recente pra projetar."""

    if not distance_km or weeks_left is None or weeks_left < _MIN_WEEKS_LEFT:

        return None

    recent_week_values = weekly_km[-_WINDOW:]

    previous_week_values = weekly_km[-2 * _WINDOW:-_WINDOW]

    recent_week = _running_mean(recent_week_values)

    if recent_week is None:

        return None

    previous_week = _running_mean(previous_week_values)

    week_slope = (recent_week - previous_week) / _WINDOW if previous_week is not None else 0.0

    recent_long = max(longest_km[-_WINDOW:] or [0.0])

    previous_long = max(longest_km[-2 * _WINDOW:-_WINDOW] or [0.0])

    best_long = max(longest_km or [0.0])

    long_slope = (recent_long - previous_long) / _WINDOW if previous_long else 0.0

    # "se seguir no passo das últimas semanas": só sobe (queda recente não vira projeção de queda)
    best_week = max(weekly_km or [0.0])

    projected_week = min(
        recent_week + max(0.0, week_slope) * weeks_left,
        max(best_week, recent_week) * _PROJECTION_CAP,
    )

    projected_long = min(
        recent_long + max(0.0, long_slope) * weeks_left,
        max(best_long, recent_long) * _PROJECTION_CAP,
    )

    long_ref, week_ref = reference_for(distance_km)

    # com 3 corridas ou menos por semana o volume de referência é o piso da faixa
    week_target = week_ref[0] if runs_per_week <= 3 else (week_ref[0] + week_ref[1]) / 2

    return GoalPath(
        weeks_left=weeks_left,
        distance_km=distance_km,
        target_time=target_time,
        long_ref=long_ref,
        week_ref=week_ref,
        recent_long=recent_long,
        best_long=best_long,
        recent_week=recent_week,
        best_week=best_week,
        projected_long=projected_long,
        projected_week=projected_week,
        long_gap=max(0.0, long_ref[0] - projected_long),
        week_gap=max(0.0, week_target - projected_week),
        runs_per_week=runs_per_week,
        hard_pct=hard_pct,
    )


def _km(value: float) -> str:

    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}".replace(".", ",")


def _distance(km: float) -> str:

    return f"{round(km, 1):g}".replace(".", ",")


def _facts(path: GoalPath) -> str:

    target = f" em {path.target_time}" if path.target_time else ""

    hard = (
        f" {path.hard_pct}% do tempo em zona forte nas últimas 4 semanas (pela FC média de cada "
        "corrida: tiro com pausa aparece mais leve)."
        if path.hard_pct is not None
        else ""
    )

    aim = "no piso" if path.runs_per_week <= 3 else "no meio da faixa"

    return (
        f"faltam {path.weeks_left} semanas pra {_distance(path.distance_km)} km{target}. "
        f"Pra um amador bater um tempo nessa distância o preparo costuma chegar a um longão de "
        f"~{path.long_ref[0]}-{path.long_ref[1]} km e ~{path.week_ref[0]}-{path.week_ref[1]} "
        f"km/semana no pico (com {path.runs_per_week} corridas por semana, mire {aim}). "
        f"Hoje ele está em: maior treino recente {_km(path.recent_long)} km (o maior em 8 "
        f"semanas, {_km(path.best_long)}), ~{_km(path.recent_week)} km por semana em semana de "
        f"corrida (a melhor, {_km(path.best_week)}).{hard} Se seguir no passo das últimas "
        f"semanas chega na prova com longão de ~{_km(path.projected_long)} km e "
        f"~{_km(path.projected_week)} km/semana"
    )


def goal_path_directive(path: GoalPath | None) -> str:
    """O sinal pro PLANO: a diferença a fechar. Vazio sem rota."""

    if path is None:

        return ""

    # nenhum esforço forte medido: a capacidade real é desconhecida (Leonardo: Garmin 56:37 ×
    # treinos 1:05:32, sem um esforço que decida) — o teste é uma ideia, a decisão é do coach
    unknown = (
        " Nenhum esforço forte medido nas últimas semanas: a capacidade real dele é "
        "desconhecida — um teste curto e controlado (ex.: 3 km em esforço forte ou 3×1,5 km) "
        "calibra o limiar e o ritmo de prova de verdade; a decisão é sua."
        if path.hard_pct == 0
        else ""
    )

    gaps = []

    if path.long_gap >= _MIN_GAP_KM:

        gaps.append(f"~{round(path.long_gap)} km no longão")

    if path.week_gap >= _MIN_GAP_KM:

        gaps.append(f"~{round(path.week_gap)} km por semana")

    head = (
        "ROTA ATÉ A META (mais um insumo pra você, o COACH — hipótese de treinador em faixa, "
        f"não decreto): {_facts(path)}"
    )

    if not gaps:

        return (
            f"{head} — a trajetória cobre a referência: mantenha o passo e leve a qualidade "
            f"específica (limiar/ritmo de prova) pras semanas finais.{unknown}"
        )

    return (
        f"{head} → FALTAM {' e '.join(gaps)}. É a DIFERENÇA a fechar nas {path.weeks_left} "
        "semanas que restam: distribua em degraus, o primeiro JÁ nesta semana (volume semanal "
        "segue o limite do salto, ~+10-15% por semana, e descarga só quando o corpo pedir), "
        "priorizando o que a meta mais cobra e que ele ainda não fez. Se não couber com "
        "segurança, diga isso a ele e proponha ajustar a meta. Repetir a semana anterior sem "
        f"dizer por quê é o único erro.{unknown}"
    )


def goal_path_fact(path: GoalPath | None) -> str:
    """O mesmo como FATO CURTO pras vozes que não montam o plano (chat, análise, resumos): serve
    pra responder "estou no caminho?" com número, sem instrução de dose."""

    if path is None:

        return ""

    gaps = []

    if path.long_gap >= _MIN_GAP_KM:

        gaps.append(f"~{round(path.long_gap)} km no longão")

    if path.week_gap >= _MIN_GAP_KM:

        gaps.append(f"~{round(path.week_gap)} km por semana")

    tail = (
        f" — faltam {' e '.join(gaps)} pra referência."
        if gaps
        else " — a trajetória cobre a referência."
    )

    return (
        f"Rota até a meta (hipótese de treinador, não promessa): {_facts(path)}{tail} Se ele "
        "perguntar se está no caminho, responda com isto e com a faixa de previsão."
    )
