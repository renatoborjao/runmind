"""BASE DA SEMANA + CONFERENTE DO PLANO — sem IA, puro, com os números do atleta.

Por quê (Renato, 16/11): o plano saía com números que o próprio dado desmentia — limiar 6:10-6:20
chamado de "mais firme" com o limiar calibrado em 5:49 e a meta a 6:00; volume parado semanas a fio
pra quem entrega. Os apps que acertam (Runna, Garmin Coach) CALCULAM os números do dado (ritmo pelo
desempenho real, volume por um teto semanal, longão por progressão própria) e ajustam pelo que o
atleta entrega. Aqui a IA continua decidindo a forma da semana — mas parte de uma BASE calculada e
passa por um CONFERENTE antes do envio.

Economia (Renato: "o mínimo de regeneração possível"):
  - a BASE vai curta no topo do contexto, pra a IA acertar de primeira;
  - só erro GRAVE e inequívoco (HIGH) volta pra IA, UMA vez, com os números — ela corrige ou mantém
    justificando; o resto (WATCH) só vira aviso pro dono no monitor de domingo;
  - cada conferência é registrada no log ("Conferente:") pra medir a taxa de refação.

Referências: ritmos por VDOT (Daniels' Running Formula, fórmulas de domínio público em
`vdot_calculator`); subir o VDOT ~1 ponto a cada 4-6 semanas de treino consistente (Daniels); salto
de UMA corrida >10% sobre a maior dos 30 dias é o maior previsor de lesão (Frandsen et al., BJSM
2025); teto semanal de volume ~10%."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.history.stimulus_dose import main_lines, pace_band
from app.application.history.stimulus_ledger import (
    EASY,
    LONG,
    RACE_PACE,
    THRESHOLD,
    VO2,
    StimulusLedger,
)
from app.application.history.vdot_calculator import FRAC_THRESHOLD, VdotCalculator

HIGH = "high"
WATCH = "watch"

# tolerâncias (s/km) — largas de propósito: só o erro claro dispara
PACE_TOL_S = 10
EASY_TOL_S = 20

# quem entrega: a semana nova não fica abaixo de tanto do que ele FEZ (sem motivo escrito)
FROZEN_RATIO = 0.95

# quem NÃO entrega: a semana nova não passa de tanto acima da MELHOR semana recente dele (uma
# semana furada é contexto — o que ele sustentou antes é o que ele volta a sustentar)
CLIMB_RATIO = 1.10

# quantas semanas fechadas contam pro "que ele sustenta"
SUSTAIN_WEEKS = 4

# o maior treino não passa de tanto sobre o maior dos últimos 30 dias
LONG_SPIKE = 1.10

# faixa de volume da semana pra quem entrega (sobre o que ele fez)
STEP_LOW, STEP_HIGH = 1.05, 1.10

# ganho realista de VDOT: ~1 ponto a cada 4-6 semanas de treino consistente (Daniels)
WEEKS_PER_VDOT = 5

_RUN_KINDS = ("run", "walk", "run_walk")


@dataclass(slots=True)
class CheckFacts:
    """O que o atleta É e FEZ, em números (min/km e km). Falta de dado = None/0: o check cala."""

    threshold: float | None = None
    vo2: float | None = None
    easy_fast: float | None = None
    race_goal: float | None = None
    goal_km: float | None = None
    goal_seconds: int | None = None
    weeks_to_race: int | None = None
    delivering: bool = False
    last_done_km: float = 0.0
    last_planned_km: float = 0.0
    # das últimas semanas fechadas em que correu: a mediana e a melhor (km)
    sustained_km: float = 0.0
    best_recent_km: float = 0.0
    longest_30d_km: float = 0.0


@dataclass(slots=True)
class Issue:

    code: str
    level: str
    text: str


def _fmt(pace: float) -> str:

    total = round(pace * 60)

    return f"{total // 60}:{total % 60:02d}"


def _clock(seconds: float) -> str:

    seconds = round(seconds)

    h, rest = divmod(seconds, 3600)

    m, s = divmod(rest, 60)

    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def reference_km(f: "CheckFacts") -> float:
    """De onde a semana nova parte pra quem ENTREGA: o menor entre o planejado e o feito — a carga
    extra que ele fez além do plano não vira degrau (Mauricio: 50 km com 38 planejados)."""

    if f.last_planned_km > 0 and f.last_done_km > 0:

        return min(f.last_planned_km, f.last_done_km)

    return f.last_done_km


def _km(value: float) -> str:

    return f"{value:.1f}".replace(".", ",").replace(",0", "") + " km"


# --- capacidade × meta ---------------------------------------------------------------------------


def vdot_from_threshold(threshold: float) -> float:
    """O VDOT cujo ritmo de limiar é `threshold` (min/km) — busca binária na fórmula do Daniels."""

    low, high = 15.0, 90.0

    for _ in range(60):

        mid = (low + high) / 2

        if VdotCalculator.pace_min_km(mid, FRAC_THRESHOLD) > threshold:

            low = mid

        else:

            high = mid

    return (low + high) / 2


def race_seconds(vdot: float, distance_m: float) -> float:
    """O tempo de prova que um VDOT sustenta na distância — inverte a fórmula por busca binária."""

    low, high = 60.0, 8 * 3600.0

    for _ in range(80):

        mid = (low + high) / 2

        if VdotCalculator.vdot(distance_m, mid) > vdot:

            low = mid

        else:

            high = mid

    return (low + high) / 2


def goal_reading(f: CheckFacts) -> str:
    """A meta contra a capacidade de hoje: o VDOT que ela pede, o de hoje e o ganho realista até a
    prova — e o tempo que esse ganho sustenta. Vazio sem meta de tempo ou sem limiar."""

    if not (f.goal_km and f.goal_seconds and f.threshold):

        return ""

    distance = f.goal_km * 1000

    need = VdotCalculator.vdot(distance, f.goal_seconds)

    now = vdot_from_threshold(f.threshold)

    head = (
        f"Meta {f.goal_km:g} km em {_clock(f.goal_seconds)} pede VDOT {need:.1f}; a capacidade de "
        f"hoje é VDOT {now:.1f} (sustenta ~{_clock(race_seconds(now, distance))})."
    )

    if now >= need:

        return head + " A meta JÁ cabe: o trabalho é afiar o ritmo-alvo e chegar inteiro."

    if f.weeks_to_race is None:

        weeks = (need - now) * WEEKS_PER_VDOT

        return head + (
            f" Sem prova marcada: no ritmo realista (~1 ponto a cada {WEEKS_PER_VDOT} semanas de "
            f"treino consistente) chega lá em ~{weeks:.0f} semanas — construa a base pra isso."
        )

    reach = now + f.weeks_to_race / WEEKS_PER_VDOT

    if reach >= need:

        return head + (
            f" Em {f.weeks_to_race} semanas o ganho realista (~1 ponto a cada {WEEKS_PER_VDOT}) "
            "alcança a meta: treine pra ela, subindo a régua conforme ele entrega."
        )

    return head + (
        f" Em {f.weeks_to_race} semanas o ganho realista (~1 ponto a cada {WEEKS_PER_VDOT}) leva a "
        f"VDOT ~{reach:.1f} (~{_clock(race_seconds(reach, distance))}): a meta é AGRESSIVA — treine "
        "o ritmo da meta em blocos curtos, a régua de hoje no resto, e diga a ele com esse número."
    )


# --- a base da semana (vai no topo do contexto do plano) ------------------------------------------


def base_block(f: CheckFacts) -> str:
    """Os números de partida da semana, curtos, pra a IA acertar de primeira. São os MESMOS que o
    conferente usa depois — o que estiver fora deles volta (só se for grave)."""

    lines = ["BASE DA SEMANA (números calculados do dado dele — parta daqui; a decisão é sua):"]

    zones = []

    if f.easy_fast:

        zones.append(f"leve ≥ {_fmt(f.easy_fast)}")

    if f.threshold:

        zones.append(f"limiar ~{_fmt(f.threshold)}")

    if f.vo2:

        zones.append(f"VO2 ~{_fmt(f.vo2)}")

    if f.race_goal:

        zones.append(f"ritmo da meta {_fmt(f.race_goal)}")

    if zones:

        lines.append("- Ritmos de hoje: " + " · ".join(zones) + " (min/km).")

    if f.last_done_km > 0:

        if f.delivering:

            ref = reference_km(f)

            low, high = ref * STEP_LOW, ref * STEP_HIGH

            lines.append(
                f"- Volume: ele ENTREGOU a última semana (planejou {_km(f.last_planned_km)}, fez "
                f"{_km(f.last_done_km)}). Faixa desta semana: {_km(low)}–{_km(high)} (+5 a 10% "
                "sobre o menor dos dois). Abaixo disso só com motivo em route_note."
            )

        else:

            sustained = (
                f" Nas últimas semanas ele sustentou ~{_km(f.sustained_km)} (melhor "
                f"{_km(f.best_recent_km)})."
                if f.best_recent_km > 0 else ""
            )

            lines.append(
                f"- Volume: ele NÃO entregou a última semana (fez {_km(f.last_done_km)} de "
                f"{_km(f.last_planned_km)}).{sustained} Ancore entre o que ele fez e o que ele já "
                "sustentou, pelo motivo da semana fraca (doença, viagem, sincronização…); não passe "
                "da melhor semana recente +10%."
            )

    if f.longest_30d_km > 0:

        lines.append(
            f"- Maior treino: até {_km(f.longest_30d_km * LONG_SPIKE)} (+10% sobre o maior dos 30 "
            f"dias, {_km(f.longest_30d_km)})."
        )

    reading = goal_reading(f)

    if reading:

        lines.append(f"- {reading}")

    lines.append(
        "- Faixa de cada forte nasce dos ritmos de hoje (não de segundos sobre a faixa antiga). "
        "Quem entrega sobe; quem não entrega fica no que faz."
    )

    return "\n".join(lines) if len(lines) > 2 else ""


# --- o conferente --------------------------------------------------------------------------------


def _sessions(plan) -> list:

    return [s for s in plan.sessions if getattr(s, "kind", "run") in _RUN_KINDS]


def _band(session) -> tuple[float, float] | None:

    return pace_band(
        main_lines(getattr(session, "structure", "")),
        getattr(session, "target_pace_min", None),
        getattr(session, "target_pace_max", None),
    )


def _day(session) -> str:

    return str(getattr(session, "day", "")).lower()[:3]


def check(plan, f: CheckFacts) -> list[Issue]:
    """Confere o plano contra a base. HIGH = erro claro que vale UMA revisão da IA; WATCH = só
    aviso. Puro: nada é lido nem gravado aqui."""

    out: list[Issue] = []

    sessions = _sessions(plan)

    justified = bool((getattr(plan, "route_note", None) or "").strip())

    for s in sessions:

        family = StimulusLedger.classify(s.workout_type)

        band = _band(s)

        if band is None:

            continue

        fast, slow = band

        where = f"{s.workout_type} ({_day(s)}, {_fmt(fast)}–{_fmt(slow)})"

        if family == THRESHOLD and f.threshold:

            gap = round((fast - f.threshold) * 60)

            # a meta é mais lenta que o limiar dele e a faixa é mais lenta que a meta: incoerente
            # pra qualquer atleta
            if (
                f.race_goal
                and f.race_goal >= f.threshold
                and (fast - f.race_goal) * 60 > PACE_TOL_S
            ):

                out.append(Issue("limiar_lento", HIGH, (
                    f"{where}: o limiar está mais lento que o ritmo da meta ({_fmt(f.race_goal)}) "
                    f"e {gap} s/km mais lento que o limiar de hoje dele ({_fmt(f.threshold)})."
                )))

            elif f.delivering and gap > PACE_TOL_S:

                out.append(Issue("limiar_lento", HIGH, (
                    f"{where}: {gap} s/km mais lento que o limiar de hoje dele "
                    f"({_fmt(f.threshold)}), e ele vem entregando."
                )))

        elif family == VO2 and f.vo2 and f.delivering:

            gap = round((fast - f.vo2) * 60)

            if gap > PACE_TOL_S:

                out.append(Issue("vo2_lento", WATCH, (
                    f"{where}: {gap} s/km mais lento que o VO2 de hoje dele ({_fmt(f.vo2)}), e ele "
                    "vem entregando."
                )))

        elif family == RACE_PACE and f.race_goal:

            gap = round((fast - f.race_goal) * 60)

            if gap > PACE_TOL_S:

                out.append(Issue("ritmo_prova_lento", WATCH, (
                    f"{where}: o 'ritmo de prova' está {gap} s/km mais lento que o ritmo da meta "
                    f"({_fmt(f.race_goal)})."
                )))

        elif family in (EASY, LONG) and f.easy_fast:

            gap = round((f.easy_fast - fast) * 60)

            # longão com blocos/progressão é forte de propósito: só o leve puro conta
            if gap > EASY_TOL_S and family == EASY:

                out.append(Issue("leve_forte", WATCH, (
                    f"{where}: o leve está {gap} s/km mais rápido que a ponta rápida do leve dele "
                    f"({_fmt(f.easy_fast)}) — vira mais um treino forte."
                )))

    volume = float(getattr(plan, "weekly_volume", 0) or 0) or sum(
        (s.effective_distance_km or 0.0) for s in sessions
    )

    deload = bool(getattr(plan, "is_deload", False))

    if f.last_done_km > 0 and volume > 0 and not justified and not deload:

        ref = reference_km(f)

        if f.delivering and volume < ref * FROZEN_RATIO:

            out.append(Issue("congelado", HIGH, (
                f"Ele ENTREGOU a última semana (planejou {_km(f.last_planned_km)}, fez "
                f"{_km(f.last_done_km)}) e o plano pede {_km(volume)}, sem motivo em route_note. "
                f"Quem entrega sobe (faixa {_km(ref * STEP_LOW)}–{_km(ref * STEP_HIGH)})."
            )))

        elif (
            not f.delivering
            and f.best_recent_km > 0
            and volume > f.best_recent_km * CLIMB_RATIO
        ):

            out.append(Issue("subiu_sem_entregar", HIGH, (
                f"Ele NÃO entregou a última semana (fez {_km(f.last_done_km)} de "
                f"{_km(f.last_planned_km)}) e o plano pede {_km(volume)}, acima da melhor semana "
                f"recente dele ({_km(f.best_recent_km)}) +10%, sem motivo em route_note."
            )))

    longest = max(((s.effective_distance_km or 0.0) for s in sessions), default=0.0)

    if f.longest_30d_km > 0 and longest > f.longest_30d_km * LONG_SPIKE:

        out.append(Issue("salto_longao", HIGH, (
            f"O maior treino do plano ({_km(longest)}) passa {round((longest / f.longest_30d_km - 1) * 100)}% "
            f"do maior dos últimos 30 dias ({_km(f.longest_30d_km)}); o teto é +10% "
            f"({_km(f.longest_30d_km * LONG_SPIKE)})."
        )))

    return out


def needs_revision(issues: list[Issue]) -> bool:

    return any(i.level == HIGH for i in issues)


def correction_text(issues: list[Issue]) -> str:
    """O que volta pra IA (só os HIGH): os números, e a decisão continua dela."""

    high = [i for i in issues if i.level == HIGH]

    return (
        "O CONFERENTE (números calculados do dado dele, sem IA) achou: "
        + " | ".join(i.text for i in high)
        + " Corrija esses pontos partindo da BASE DA SEMANA — ou, se o seu critério de treinador "
        "mandar manter, mantenha e escreva o motivo com números em route_note. O resto da semana "
        "pode ficar como você montou."
    )


def summary(issues: list[Issue]) -> str:

    return "; ".join(f"{i.level}:{i.code}" for i in issues) or "ok"


# --- ligação com os dados reais (best-effort) -----------------------------------------------------


def facts_for(profile: str, runner, history, metrics, goal, week_start) -> CheckFacts:
    """Os números do atleta pro conferente e a base. Só leitura; o que falhar fica no padrão e o
    check correspondente cala — nunca derruba a geração. Sem `metrics`/`goal`/`history` (o monitor
    de domingo), lê do dossiê — os mesmos números que o coach lê."""

    from datetime import timedelta

    f = CheckFacts()

    data = None

    try:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        from app.core.clock import today_local

        # "hoje" é o dia real, nunca depois da véspera da semana montada: uma semana só conta como
        # fechada quando o domingo dela chegou (o lab no meio da semana tratava os 5,7 km de uma
        # semana em andamento como "não entregou")
        today = min(today_local(), week_start - timedelta(days=1))

        data = AthleteDossier._inputs(profile, None, None, None, today)

        data.target_week = week_start

        f.delivering = AthleteDossier._is_delivering(data)

        closed = [w for w in AthleteDossier._ledger(data) if not w.in_progress and w.planned_km > 0]

        if closed:

            f.last_planned_km, f.last_done_km = closed[-1].planned_km, closed[-1].done_km

        recent = [
            w.done_km for w in AthleteDossier._ledger(data) if not w.in_progress and w.done_km > 0
        ][-SUSTAIN_WEEKS:]

        if recent:

            ordered = sorted(recent)

            f.sustained_km = ordered[len(ordered) // 2]

            f.best_recent_km = ordered[-1]

    except Exception as e:  # noqa: BLE001

        print(f"Conferente: semanas anteriores falharam p/ '{profile}': {e}")

    metrics = metrics if metrics is not None else getattr(data, "metrics", None)

    goal = goal if goal is not None else getattr(data, "goal", None)

    if metrics is not None:

        f.threshold = float(getattr(metrics, "threshold_pace", 0) or 0) or None

        f.vo2 = float(getattr(metrics, "vo2_pace", 0) or 0) or None

        f.easy_fast = float(getattr(metrics, "easy_pace_min", 0) or 0) or None

    try:

        from app.application.coach.planning.plan_context_builder import PlanContextBuilder

        secs = PlanContextBuilder._time_to_seconds(getattr(goal, "target_time", None))

        km = getattr(goal, "distance_km", None)

        if secs and km:

            f.goal_seconds, f.goal_km = secs, float(km)

            f.race_goal = secs / 60 / km

        race_date = getattr(goal, "race_date", None)

        if race_date is not None and race_date >= week_start:

            f.weeks_to_race = max(0, (race_date - week_start).days // 7)

    except Exception as e:  # noqa: BLE001

        print(f"Conferente: meta ilegível p/ '{profile}': {e}")

    try:

        from app.application.history.weekly_buckets import activity_date
        from app.domain.value_objects.sports import is_run_sport

        activities = getattr(history, "activities", None) or getattr(data, "activities", None) or []

        start = week_start - timedelta(days=30)

        f.longest_30d_km = max(
            (
                a.distance / 1000
                for a in activities
                if is_run_sport(a.sport) and start <= activity_date(a) < week_start
            ),
            default=0.0,
        )

    except Exception as e:  # noqa: BLE001

        print(f"Conferente: maior treino falhou p/ '{profile}': {e}")

    return f
