"""ROTA SEMANA A SEMANA — o macrociclo que faltava: pra cada semana até a prova (ou as próximas 8,
sem prova com data), quanto de volume, de longão, de qualidade e de trabalho no ritmo da prova, e
qual o foco do estímulo.

O coach montava UMA semana por vez, ancorado na anterior: o macro existia só como fases (o mapa
até a prova, sem números) e como extremos (a rota até a meta). Faltava o meio, e o resultado era
um plano estagnado — mesmo longão, mesma dose, o forte só trocando de nome — ou em dente de serra
(Leonardo: 8 km → 22 km → 6 km; o volume subia e caía sem desenho). Aqui sai a CURVA: parte do que
o atleta FEZ (nunca do papel), sobe todo semana enquanto ele cumpre, planeja o polimento e o
simulado, e gira o foco do estímulo de propósito (limiar → VO2 → subidas → ritmo de prova) pra
haver variação de força, ritmo e distância.

É GUIA, não trilho ([[feedback_ia_decide_sem_regras]]): o coach segue o que o corpo pede e se
afasta com MOTIVO escrito; a rota se refaz todo domingo a partir do executado; recuo só quando o
corpo pede (nenhuma descarga por calendário). Os números são hipótese de treinador em faixa, a
mesma régua da rota até a meta ([[goal_path]]). Puro/determinístico, sem IA."""

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from app.application.coach.planning.race_map import (
    BASE,
    BUILD,
    MINI,
    RECOVERY,
    SIMULATED,
    SPECIFIC,
    TAPER,
    taper_weeks,
)
from app.application.history.goal_path import reference_for

ROLLING_WEEKS = 8

# crescimento máximo do volume por semana: com folga demonstrada (cumpre com esforço baixo e/ou
# pediu mais) o teto é o do salto seguro; sem folga, mais prudente
GROWTH_MAX = 0.10
GROWTH_MAX_STEADY = 0.07
GROWTH_MAX_ROLLING = 0.08

# sem prova com data e sem meta de distância: no máximo isto acima do que ele já sustenta
_ROLLING_CAP = 1.35

# faixa ao redor do volume da rota: dentro dela o coach segue o corpo sem justificar
BAND = 0.10

LONG_STEP_MAX = 1.0

QUALITY_STEP_MAX = 1.5

# a dose de qualidade no pico (km de trabalho forte, sem aquecer/soltar) por distância da prova
_QUALITY_PEAK = ((5.5, 6.0), (10.5, 8.0), (16.0, 10.0), (22.0, 12.0), (99.0, 14.0))

_TAPER_FACTORS = {1: (0.55,), 2: (0.75, 0.55), 3: (0.8, 0.6, 0.45)}

_SIMULATED_FACTOR = 0.9

_MINI_FACTOR = 0.7

_RECOVERY_FACTOR = 0.8

# na semana da prova: a distância dela + este tanto de trote/soltura antes
_RACE_WEEK_EXTRA_KM = 4.0

# volta de parada ≥ 14 dias: as duas primeiras semanas são retomada
_RETURN_LAYOFF_DAYS = 14

_RETURN_FACTORS = (0.6, 0.8)

# quem corre sem meta de tempo precisa de menos que a referência de quem quer bater um tempo
_FINISH_FACTOR = 0.85

# o longão não pesa mais que isto do volume sem aviso
_LONG_SHARE_NOTE = 0.55

_FOCUS = {
    BASE: ("aeróbico com acelerações", "subidas curtas (força) + aeróbico", "fartlek leve"),
    BUILD: (
        "limiar",
        "VO2 / velocidade",
        "subidas e força",
        "limiar mais longo",
        "ritmo de prova (introdução)",
    ),
    SPECIFIC: (
        "ritmo de prova em blocos",
        "ritmo de prova contínuo, bloco maior",
        "ritmo de prova + limiar",
    ),
    SIMULATED: ("simulado: o longão vira o teste no ritmo de prova",),
    TAPER: ("toques curtos no ritmo de prova; descanso",),
    MINI: ("soltar a perna; a prova preparatória é o treino forte",),
    RECOVERY: ("volta gradual; sem forte nos primeiros dias",),
}

_LONG_FORMS = (
    "só aeróbico, +km",
    "mesmo km com final progressivo",
    "só aeróbico, +km",
    "final em blocos no ritmo-alvo",
)

# qualidade por fase, em fração da dose do degrau
_QUALITY_SHARE = {
    BASE: 0.6,
    BUILD: 1.0,
    SPECIFIC: 1.0,
    SIMULATED: 1.0,
    TAPER: 0.5,
    MINI: 0.5,
    RECOVERY: 0.3,
}

# do trabalho de qualidade, quanto é NO RITMO DA PROVA
_SPECIFIC_SHARE = {BASE: 0.0, BUILD: 0.35, SPECIFIC: 0.7, TAPER: 0.0, MINI: 0.0, RECOVERY: 0.0}

_SHORT = {
    BASE: "base",
    BUILD: "construção",
    SPECIFIC: "ritmo de prova",
    SIMULATED: "simulado",
    TAPER: "polimento e prova",
    MINI: "mini-polimento e prova",
    RECOVERY: "recuperação",
}


@dataclass(slots=True)
class RouteWeek:

    index: int
    week_start: date
    phase: str
    volume_km: float
    volume_lo: float
    volume_hi: float
    long_km: float
    quality_km: float
    specific_km: float
    focus: str
    note: str = ""


@dataclass(slots=True)
class WeeklyRoute:

    weeks: list[RouteWeek]
    baseline_km: float
    baseline_long_km: float
    peak_km: float
    peak_long_km: float
    growth_pct: float
    rolling: bool
    distance_km: float | None
    target_time: str | None
    race_date: date | None
    peak_date: date
    basis: str


def _quality_peak(distance_km: float) -> float:

    for limit, value in _QUALITY_PEAK:

        if distance_km <= limit:

            return value

    return _QUALITY_PEAK[-1][1]


def baseline_km(executed_weeks: list[float]) -> tuple[float, str] | None:
    """O que ele SUSTENTA, do que ele FEZ: a mediana das 4 últimas semanas com corrida, ou 90% da
    segunda melhor das 6 (o que vier maior) — a melhor semana isolada (treino extra, uma vez) não
    vira chão. None sem corrida."""

    ran = [w for w in executed_weeks if w > 0]

    if not ran:

        return None

    recent = median(ran[-4:])

    last = sorted(ran[-6:])

    second = last[-2] if len(last) >= 2 else last[-1]

    value = max(recent, 0.9 * second)

    basis = (
        f"mediana das últimas semanas com corrida (~{recent:.0f} km) e a segunda melhor "
        f"(~{second:.0f} km)"
    )

    return value, basis


def _keys(phases: list[str] | None) -> tuple[list[str], bool]:

    if phases:

        return list(phases), False

    return [BUILD] * ROLLING_WEEKS, True


def _peak_index(keys: list[str]) -> int:
    """A semana em que a rota chega no pico: a última de ritmo de prova (a carga ainda sobe nelas);
    sem ritmo de prova, a que antecede o simulado/polimento; sem nenhum dos dois, a última."""

    specific = [i for i, k in enumerate(keys) if k == SPECIFIC]

    if specific:

        return specific[-1]

    ahead = next((i for i, k in enumerate(keys) if k in (SIMULATED, TAPER)), None)

    if ahead is None:

        return len(keys) - 1

    return max(0, ahead - 1)


def build(
    *,
    ref_week: date,
    phases: list[str] | None,
    distance_km: float | None,
    target_time: str | None,
    race_date: date | None,
    executed_weeks: list[float],
    longest_runs: list[float],
    quality_done_km: float = 0.0,
    runs_per_week: int = 3,
    layoff_days: int = 0,
    slack: bool = False,
) -> WeeklyRoute | None:
    """A rota a partir da semana `ref_week`. `phases`: a fase de cada semana até a prova (as do
    mapa até a prova; uma por semana, a última é a da prova); None = sem prova com data → as
    próximas 8 semanas, rolantes. `executed_weeks`/`longest_runs`: as últimas semanas FECHADAS (da
    mais antiga pra mais recente, 0 = sem corrida). `slack`: ele cumpre com folga ou pediu mais."""

    base = baseline_km(executed_weeks)

    if base is None:

        return None

    start_km, basis = base

    keys, rolling = _keys(phases)

    total = len(keys)

    peak_idx = _peak_index(keys)

    steps = peak_idx + 1

    growth_max = GROWTH_MAX if slack else GROWTH_MAX_STEADY

    if rolling:

        growth_max = min(growth_max, GROWTH_MAX_ROLLING)

    distance = distance_km or (None if rolling else 10.0)

    finish = _FINISH_FACTOR if not target_time else 1.0

    long_ref = (0.0, 0.0)

    if distance:

        long_ref, week_ref = reference_for(distance)

        week_target = (
            week_ref[0] if runs_per_week <= 3 else (week_ref[0] + week_ref[1]) / 2
        ) * finish

    else:

        week_target = start_km * _ROLLING_CAP

    reach = start_km * (1 + growth_max) ** steps

    peak = max(start_km, min(week_target, reach))

    growth = (peak / start_km) ** (1 / steps) - 1

    level = [start_km * (1 + growth) ** min(i + 1, steps) for i in range(total)]

    # longão: de onde ele está até o meio da faixa da distância, no máximo +1 km por semana
    long_runs = [v for v in longest_runs if v > 0]

    long_now = max(max(longest_runs[-4:] or [0.0]), 0.9 * max(long_runs or [0.0]))

    if long_now <= 0:

        long_now = 0.4 * start_km

    long_goal = (long_ref[0] + long_ref[1]) / 2 * finish if distance else long_now + steps * 0.5

    long_peak = max(long_now, min(long_goal, long_now + LONG_STEP_MAX * steps))

    quality_now = max(2.0, 0.5 * quality_done_km) if quality_done_km > 0 else 3.0

    quality_goal = _quality_peak(distance or 10.0) * finish

    quality_peak = max(quality_now, min(quality_goal, quality_now + QUALITY_STEP_MAX * steps))

    taper_count = sum(1 for k in keys if k == TAPER)

    factors = _TAPER_FACTORS[taper_weeks(distance)] if taper_count else ()

    if taper_count and len(factors) < taper_count:

        factors = (factors[0],) * (taper_count - len(factors)) + factors

    factors = factors[-taper_count:] if taper_count else ()

    last_pre = max((i for i, k in enumerate(keys) if k != TAPER), default=0)

    seen: dict[str, int] = {}

    taper_seen = 0

    share_noted = False

    weeks: list[RouteWeek] = []

    for i, key in enumerate(keys):

        ramp = min(i + 1, steps) / steps

        long_now_i = long_now + (long_peak - long_now) * ramp

        quality_i = (quality_now + (quality_peak - quality_now) * ramp) * _QUALITY_SHARE[key]

        quality_i = max(quality_i, 0.0)

        volume = level[i]

        long_km = long_now_i

        specific = quality_i * _SPECIFIC_SHARE.get(key, 0.0)

        note = ""

        if key == SIMULATED:

            volume *= _SIMULATED_FACTOR

            long_km = min(long_peak, 0.8 * (distance or 10.0))

            specific = min(0.6 * (distance or 10.0), 12.0)

        elif key == TAPER:

            volume = level[last_pre] * factors[taper_seen]

            long_km = long_peak * factors[taper_seen]

            taper_seen += 1

            if i == total - 1:

                # a prova é o longão — e a semana nunca tem menos que a prova mais um trote antes
                volume = max(volume, (distance or 10.0) + _RACE_WEEK_EXTRA_KM)

                long_km = 0.0

                note = "semana da prova: a prova é o longão"

        elif key == MINI:

            volume *= _MINI_FACTOR

            long_km *= _MINI_FACTOR

            note = "prova preparatória: mini-polimento"

        elif key == RECOVERY:

            volume *= _RECOVERY_FACTOR

            long_km *= _RECOVERY_FACTOR

            note = "volta gradual depois da prova"

        if layoff_days >= _RETURN_LAYOFF_DAYS and i < len(_RETURN_FACTORS):

            volume *= _RETURN_FACTORS[i]

            long_km *= _RETURN_FACTORS[i]

            quality_i *= _RETURN_FACTORS[i]

            specific *= _RETURN_FACTORS[i]

            note = "retomada depois de parada: comece leve"

        if long_km > _LONG_SHARE_NOTE * volume and not note and not share_noted:

            share_noted = True

            note = (
                f"o longão é {long_km / volume * 100:.0f}% da semana: o volume sobe pelas corridas "
                "curtas (mais uma corrida), sem cortar o longão"
            )

        count = seen.get(key, 0)

        seen[key] = count + 1

        focus = _FOCUS[key][count % len(_FOCUS[key])]

        if key in (BUILD, SPECIFIC) and long_km:

            focus += f"; longão: {_LONG_FORMS[i % len(_LONG_FORMS)]}"

        weeks.append(
            RouteWeek(
                index=i + 1,
                week_start=ref_week + timedelta(weeks=i),
                phase=key,
                volume_km=volume,
                volume_lo=volume * (1 - BAND),
                volume_hi=volume * (1 + BAND),
                long_km=long_km,
                quality_km=quality_i,
                specific_km=specific,
                focus=focus,
                note=note,
            )
        )

    return WeeklyRoute(
        weeks=weeks,
        baseline_km=start_km,
        baseline_long_km=long_now,
        peak_km=peak,
        peak_long_km=long_peak,
        growth_pct=growth * 100,
        rolling=rolling,
        distance_km=distance,
        target_time=target_time,
        race_date=race_date,
        peak_date=ref_week + timedelta(weeks=peak_idx),
        basis=basis,
    )


def week_for(route: WeeklyRoute | None, week_start: date) -> RouteWeek | None:

    if route is None:

        return None

    return next((w for w in route.weeks if w.week_start == week_start), None)


# --- o que o plano guarda --------------------------------------------------------------------


def snapshot(route: WeeklyRoute | None, weeks: int = 4) -> dict | None:
    """A rota que o coach tinha à frente ao montar o plano (as próximas `weeks` semanas) — fica
    guardada com ele pra a semana seguinte e a auditoria compararem planejado × feito."""

    if route is None:

        return None

    return {
        "v": 1,
        "rolling": route.rolling,
        "weeks": [
            {
                "w": w.week_start.isoformat(),
                "ph": w.phase,
                "km": [round(w.volume_lo, 1), round(w.volume_hi, 1)],
                "vol": round(w.volume_km, 1),
                "long": round(w.long_km, 1),
                "q": round(w.quality_km, 1),
            }
            for w in route.weeks[:weeks]
        ],
    }


# --- o que o coach lê ------------------------------------------------------------------------


def _km(value: float) -> str:

    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}".replace(".", ",")


def _week_line(week: RouteWeek) -> str:

    label = _SHORT[week.phase]

    text = (
        f"- sem {week.index} ({week.week_start:%d/%m} · {label}): ~{_km(week.volume_km)} km "
        f"({_km(week.volume_lo)}–{_km(week.volume_hi)})"
    )

    if week.long_km:

        text += f" · longão ~{_km(week.long_km)} km"

    if week.quality_km >= 0.5:

        text += f" · qualidade ~{_km(week.quality_km)} km"

        if week.specific_km >= 0.5:

            text += f" (no ritmo de prova ~{_km(week.specific_km)})"

    text += f" · foco sugerido: {week.focus}"

    if week.note:

        text += f" [{week.note}]"

    return text


def _later(weeks: list[RouteWeek]) -> str:
    """O resto da rota, por fase (o detalhe é só das próximas semanas)."""

    groups: list[list[RouteWeek]] = []

    for week in weeks:

        if groups and groups[-1][0].phase == week.phase:

            groups[-1].append(week)

        else:

            groups.append([week])

    parts = []

    for group in groups:

        first, last = group[0], group[-1]

        label = _SHORT[first.phase]

        when = (
            f"{first.week_start:%d/%m}"
            if len(group) == 1
            else f"{first.week_start:%d/%m}–{last.week_start:%d/%m}"
        )

        lo, hi = min(w.volume_km for w in group), max(w.volume_km for w in group)

        size = _km(lo) if abs(hi - lo) < 0.5 else f"{_km(lo)}–{_km(hi)}"

        parts.append(f"{label} {when} (~{size} km)")

    return "; ".join(parts)


_HOW_TO_USE = (
    "COMO USAR: a rota se REFAZ todo domingo a partir do que ele FEZ e SOBE enquanto ele cumpre — "
    "repetir a semana anterior não é prudência, é sair da rota. Dentro de ±20% do volume dela, "
    "siga "
    "o que o corpo e a forma pedem sem precisar justificar; FORA disso a semana precisa de MOTIVO "
    "(corpo, doença, viagem, prova, o que ele não cumpriu) — escreva em \"route_note\", 1 frase "
    "com "
    "números. O LONGÃO também segue a rota: se o desta semana ficar abaixo do maior recente dele "
    "ou do da rota (sobe ~0,5 km por semana), diga por quê no mesmo \"route_note\". O papel que "
    "o bloco deu a esta semana foi escrito semanas antes: se diverge da fase da rota (ex.: "
    "simulado longe da prova), a rota e o corpo de hoje mandam — redefina \"block\". Recuar: só "
    "quando o corpo pedir (nunca por calendário). A VARIAÇÃO é de propósito "
    "— o "
    "foco sugerido gira (limiar → VO2 → subidas/força → ritmo de prova) e o longão muda de forma; "
    "troque o foco só com razão (lacuna, corpo, preferência dele), mas NÃO repita o mesmo estímulo "
    "com a mesma dose. Ritmo, força e distância evoluem JUNTOS: a dose sobe, o ritmo chega mais "
    "perto "
    "do alvo."
)


def render(route: WeeklyRoute | None, *, detail: int = 4, directive: bool = True) -> str:
    """O bloco do dossiê: as próximas `detail` semanas em detalhe, o resto por fase. `directive`
    (voz do plano) acrescenta como usar; as outras vozes recebem só os fatos (2 semanas)."""

    if route is None or not route.weeks:

        return ""

    where = (
        f"as próximas {len(route.weeks)} semanas (rolante, sem prova com data)"
        if route.rolling
        else f"até a prova em {route.race_date:%d/%m}"
    )

    head = (
        f"ROTA SEMANA A SEMANA (guia — hipótese de treinador, NÃO trilho) {where}. Ponto de "
        f"partida = o que ele FEZ (~{_km(route.baseline_km)} km/semana; {route.basis}; longão "
        f"~{_km(route.baseline_long_km)} km) → pico de ~{_km(route.peak_km)} km/semana e longão de "
        f"~{_km(route.peak_long_km)} km em {route.peak_date:%d/%m} "
        f"({route.growth_pct:+.0f}% por semana até lá):"
    )

    shown = route.weeks[: detail if directive else 2]

    lines = [head] + [_week_line(w) for w in shown]

    rest = route.weeks[len(shown):]

    if rest and directive:

        lines.append(f"- Depois: {_later(rest)}.")

    if directive:

        lines.append(_HOW_TO_USE)

    return "\n".join(lines)


__all__ = [
    "BAND",
    "RouteWeek",
    "WeeklyRoute",
    "baseline_km",
    "build",
    "render",
    "snapshot",
    "week_for",
]
