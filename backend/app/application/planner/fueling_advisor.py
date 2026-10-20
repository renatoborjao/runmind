"""NUTRIÇÃO NO TREINO LONGO — quando o atleta deve tomar gel (ou derivados) pra repor.

Determinístico, sem IA: a dose é conhecimento de fisiologia do esporte, não palpite.
Referência (ACSM / ISSN): abaixo de ~1h o carboidrato não faz diferença; entre 1h e
2h30, 30–60 g por hora; mais que isso, até 60–90 g/h. Um gel padrão traz ~25 g. Os
horários saem da DURAÇÃO estimada da sessão (passos do plano quando existem; senão
km × pace-alvo) — o longão de 10 km e o de 16 km não recebem a mesma orientação.

Honestidade: sessão curta (< 75 min) não ganha linha nenhuma. Quem declarou diabetes
ou condição parecida nas restrições da Nutrição recebe só o encaminhamento ao
médico/nutricionista (nada de dose). Quem escreveu que não gosta de gel recebe o mesmo
horário com os derivados no lugar. Ver [[project_cardapio_treinos]]."""

from __future__ import annotations

import re

from app.application.nutrition.training_profile import session_load

# abaixo disso a sessão não precisa repor nada
MIN_MINUTES = 75

# a partir daqui a reposição vira cronograma (antes disso é "opcional", 1 gel)
SCHEDULE_FROM_MINUTES = 95

# a partir daqui o intervalo encurta (corrida realmente longa)
VERY_LONG_MINUTES = 150

GEL_CARBS_G = 25

# o último gel sai pelo menos X min antes do fim (não adianta repor no desaquecimento)
_LAST_GEL_BEFORE_END = 15

_FALLBACK_PACE = 6.5  # min/km, quando o passo não traz alvo

_MEDICAL = re.compile(
    r"diabet|insulin|hipoglic|hipoglic|glicemi|metformina", re.IGNORECASE
)

_NO_GEL = re.compile(
    r"gel|gomin|n[aã]o (tolero|aguento|curto|gosto)|enjo[ao]|intoler", re.IGNORECASE
)

_REHEARSAL = re.compile(r"simulado|ritmo de prova|prova", re.IGNORECASE)

_ALTERNATIVES = "2 balas de goma, 1 banana ou isotônico"


def _parse_pace(raw) -> float | None:

    try:

        minutes, seconds = str(raw).strip().split(":")[:2]

        return int(minutes) + int(seconds) / 60

    except (ValueError, TypeError, AttributeError):

        return None


def _mid(low, high) -> float | None:

    values = [v for v in (_parse_pace(low), _parse_pace(high)) if v]

    return sum(values) / len(values) if values else None


# passos de aquecer/soltar/recuperar andam em ritmo leve, não no pace da série
_EASY_KINDS = {"warmup", "cooldown", "recovery", "rest"}


def _steps_minutes(steps, session_pace: float | None) -> float:

    total = 0.0

    for step in steps or []:

        if getattr(step, "is_repeat", False):

            total += (step.reps or 1) * _steps_minutes(step.steps, session_pace)

        elif step.duration_sec:

            total += step.duration_sec / 60

        elif step.distance_m:

            own = _mid(step.pace_min, step.pace_max)

            if own is None:

                own = (
                    _FALLBACK_PACE
                    if step.kind in _EASY_KINDS or session_pace is None
                    else session_pace
                )

            total += (step.distance_m / 1000) * own

    return total


def estimated_minutes(session) -> int | None:
    """Duração estimada da sessão (min): soma dos passos quando o plano os traz
    (aquecimento + série + desaquecimento, cada um no seu pace); senão km × pace
    do alvo. None se não dá pra estimar."""

    steps = getattr(session, "steps", None)

    if steps:

        session_pace = _mid(
            getattr(session, "target_pace_min", None),
            getattr(session, "target_pace_max", None),
        )

        minutes = _steps_minutes(steps, session_pace)

        if minutes > 0:

            return int(round(minutes))

    _, minutes = session_load(session)

    return minutes


def schedule(minutes: int) -> list[int]:
    """Em que minuto tomar cada gel. Sessões entre MIN e SCHEDULE_FROM: 1 gel perto
    da metade (opcional); depois, a cada ~35 min (a cada ~30 acima de 2h30), do min
    35 (30) em diante, o último pelo menos 15 min antes do fim."""

    if minutes < MIN_MINUTES:

        return []

    if minutes < SCHEDULE_FROM_MINUTES:

        return [5 * round(minutes * 0.5 / 5)]

    first, every = (30, 30) if minutes >= VERY_LONG_MINUTES else (35, 35)

    times = [first]

    while times[-1] + every <= minutes - _LAST_GEL_BEFORE_END:

        times.append(times[-1] + every)

    return times


def _join(times: list[int]) -> str:

    if len(times) == 1:

        return f"{times[0]}"

    return ", ".join(str(t) for t in times[:-1]) + f" e {times[-1]}"


def _restrictions_text(profile: str | None) -> str:

    if not profile:

        return ""

    try:

        from app.infrastructure.persistence.nutrition_repository import (
            NutritionRepository,
        )

        settings = NutritionRepository().load(profile).get("settings") or {}

        return f"{settings.get('restrictions') or ''} {settings.get('dislikes') or ''}"

    except Exception as e:  # noqa: BLE001

        print(f"Nutrição no longão: restrições indisponíveis p/ '{profile}': {e}")

        return ""


def _alert_tip(times: list[int], no_gel: bool) -> str:
    """Como NÃO esquecer: um alerta de tempo recorrente no relógio (recurso nativo do
    Garmin, configurado uma vez nas opções da atividade) — sem mexer nos passos do
    treino enviado ao relógio (isso foi tentado e desfeito: muda as voltas que a
    análise pareia com o plano)."""

    moment = "de repor" if no_gel else "do gel"

    # o cronograma tem primeiro == intervalo (35, 35 / 30, 30): um alerta que repete
    # a cada N min apita exatamente nos horários
    if len(times) > 1 and times[1] - times[0] == times[0]:

        return (
            f"Dica: programe no relógio um alerta de tempo que repita a cada "
            f"{times[0]} min (nos alertas da atividade, opção Tempo) — ele apita "
            f"na hora {moment}"
        )

    what = "repor" if no_gel else "tomar o gel"

    if len(times) > 1:

        return (
            f"Dica: programe no relógio alertas de tempo aos {_join(times)} min "
            f"pra lembrar de {what}"
        )

    return (
        f"Dica: programe no relógio um alerta de tempo aos {times[0]} min pra "
        f"lembrar de {what}"
    )


def race_fueling_lines(minutes: float | None, profile: str | None = None) -> list[str]:
    """A nutrição do DIA DA PROVA — a mesma cabeça do treino: mesma fisiologia
    (< 75 min nada; 75–94 min 1 gel opcional; de 95 min cronograma), mesmo gel, mesmos
    horários e as mesmas restrições da aba Nutrição (diabetes → só o encaminhamento;
    "não curto gel" → derivados). Antes a estratégia de prova tinha uma linha própria,
    por DISTÂNCIA ("≥ 15 km: a cada ~40-45 min"), que contradizia o plano dos longões e
    ignorava as restrições — um 15 km em 1h05 mandava tomar gel e um meia mandava 40-45
    quando o treino ensinava 35. [] quando a prova é curta."""

    if not minutes:

        return []

    minutes = int(round(minutes))

    if minutes < MIN_MINUTES:

        return []

    hydrate = "Hidrate desde cedo, antes de sentir sede."

    text = _restrictions_text(profile)

    if _MEDICAL.search(text):

        return [
            "⚡ Nutrição na prova: combine com seu médico ou nutricionista quanto e "
            "quando repor carboidrato — o plano não dá dose pra quem tem essa condição. "
            + hydrate
        ]

    times = schedule(minutes)

    optional = " (opcional)" if minutes < SCHEDULE_FROM_MINUTES else ""

    no_gel = bool(_NO_GEL.search(text))

    if no_gel:

        lines = [
            f"⚡ Nutrição na prova{optional}: ~{GEL_CARBS_G} g de carboidrato aos "
            f"{_join(times)} min — como você não curte gel, use {_ALTERNATIVES}, com água"
        ]

    else:

        count = "1 gel" if len(times) == 1 else "gel"

        lines = [
            f"⚡ Nutrição na prova{optional}: {count} (~{GEL_CARBS_G} g de carboidrato) "
            f"aos {_join(times)} min, com água. Sem gel: {_ALTERNATIVES} no lugar de "
            "cada um."
        ]

    lines.append(_alert_tip(times, no_gel))

    lines.append(
        f"{hydrate} Use o MESMO gel e os mesmos horários que você testou nos "
        "longões — nada novo no dia da prova."
    )

    return lines


def fueling_lines(session, profile: str | None = None) -> list[str]:
    """As linhas de nutrição do treino ([] quando não se aplica). Entram no detalhe
    da sessão — a mensagem do plano e o app leem o MESMO texto."""

    if getattr(session, "kind", "run") not in ("run", None):

        return []

    minutes = estimated_minutes(session)

    if not minutes or minutes < MIN_MINUTES:

        return []

    text = _restrictions_text(profile)

    if _MEDICAL.search(text):

        return [
            "Nutrição: nos treinos longos, combine com seu médico ou nutricionista "
            "quanto e quando repor carboidrato — o plano não dá dose pra quem tem "
            "essa condição"
        ]

    times = schedule(minutes)

    optional = minutes < SCHEDULE_FROM_MINUTES

    if _NO_GEL.search(text):

        first = (
            f"Nutrição{' (opcional)' if optional else ''}: ~{GEL_CARBS_G} g de "
            f"carboidrato aos {_join(times)} min — como você não curte gel, "
            f"use {_ALTERNATIVES}, com água"
        )

        lines = [first]

    else:

        count = "1 gel" if len(times) == 1 else "gel"

        first = (
            f"Nutrição{' (opcional)' if optional else ''}: {count} "
            f"(~{GEL_CARBS_G} g de carboidrato) aos {_join(times)} min, com água"
        )

        lines = [
            first,
            f"Sem gel: {_ALTERNATIVES} no lugar de cada um; teste nos treinos, "
            "nunca estreie na prova",
        ]

    lines.append(_alert_tip(times, bool(_NO_GEL.search(text))))

    if _REHEARSAL.search(getattr(session, "workout_type", "") or ""):

        lines.append(
            "Esse treino é o ensaio da prova: use o MESMO gel e os mesmos horários "
            "que pretende usar no dia"
        )

    return lines
