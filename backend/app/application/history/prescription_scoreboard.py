"""PLACAR DA PRESCRIÇÃO COM ESTE ATLETA — o erro do próprio coach, como DADO.

O coach via, sessão a sessão, "alvo 6:50-7:32 → fez 6:32, FC 144" (planejado × executado), mas nunca
o RESUMO do seu próprio erro: nos leves do Leonardo, 5 de 6 saíram mais rápidos que a faixa, sempre
com a FC dentro do teto; nas voltas dos fortes, 24 de 31 mais rápidas que o alvo. Sem enxergar que o
desvio vai sempre pro mesmo lado, repetia a faixa semana após semana (placar de 01/11: só ~35% dos
paces do leve/longão na faixa, ~43% das voltas dos fortes no alvo, ~57% das distâncias em ±10%).

Aqui sai esse resumo das últimas semanas. É DADO + CONHECIMENTO, nunca regra nem correção automática
([[feedback_ia_decide_sem_regras]]): o coach decide se o alvo, a dose ou nada muda — e uma semana
ruim, um dia de calor ou uma gripe não são viés ([[feedback_adaptacao_pesa_mais_que_semana_ruim]]).
Puro/determinístico."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from app.application.history.execution_log import ExecutionLog
from app.application.history.stimulus_ledger import EASY, LONG, STEADY, STRIDES
from app.application.history.training_patterns import TrainingPatterns

WINDOW_WEEKS = 8

# abaixo disto a amostra não fala: uma corrida não é padrão
MIN_N = 3

# distância "no prescrito": até esta fração pra cima ou pra baixo
DIST_TOLERANCE = 0.10

# famílias onde a MÉDIA da corrida mede o alvo (no limiar/fartlek a média inclui aquecimento e
# trote e não diz nada: ali valem as voltas do relógio)
_PACE_FAMILIES = (EASY, LONG, STEADY)

# onde a régua do leve é a FC
_HR_FAMILIES = (EASY, LONG)

# acelerações de 100 m: o GPS não mede (erros de minutos por km)
_NO_BLOCK_STATS = (STRIDES,)

_MIN_BLOCKS = 4


@dataclass(slots=True)
class Tally:
    """Contra uma FAIXA de pace: quantas dentro, e quanto passaram da ponta (s/km)."""

    label: str
    n: int = 0
    inside: int = 0
    faster: list[int] = field(default_factory=list)       # s/km ALÉM da ponta rápida
    slower: list[int] = field(default_factory=list)       # s/km além da ponta lenta

    def add(self, gap: int) -> None:

        self.n += 1

        if gap == 0:

            self.inside += 1

        elif gap < 0:

            self.faster.append(-gap)

        else:

            self.slower.append(gap)


@dataclass(slots=True)
class Scoreboard:

    weeks: int
    prescribed: int
    done: int
    dist_n: int
    dist_within: int
    dist_over: int
    dist_under: int
    pace: list[Tally]
    hr_n: int
    hr_within: int
    ceiling: int | None
    blocks: list[Tally]
    volume: list[tuple[date, float, float]]               # (semana, prescrito, feito) — fechadas


def _sec(pace) -> int | None:

    if not pace or ":" not in str(pace):

        return None

    minutes, _, seconds = str(pace).partition(":")

    try:

        return int(minutes) * 60 + int(seconds)

    except ValueError:

        return None


def _gap(pace_s: float | None, target: str | None) -> int | None:
    """0 dentro da faixa; negativo = mais rápido que a ponta rápida; positivo = mais lento."""

    fast, _, slow = (target or "").partition("-")

    f, s = _sec(fast), _sec(slow)

    if pace_s is None or f is None or s is None:

        return None

    f, s = min(f, s), max(f, s)

    if pace_s > s:

        return round(pace_s - s)

    if pace_s < f:

        return round(pace_s - f)

    return 0


def assess(
    plans, activities, log: dict, ceiling: int | None, today: date,
    weeks: int = WINDOW_WEEKS,
) -> Scoreboard | None:
    """O placar das últimas `weeks` semanas, ou None sem nenhuma sessão prescrita na janela."""

    sessions = TrainingPatterns._sessions(plans, activities, today, weeks)

    prescribed = done = 0
    dist = {"n": 0, "within": 0, "over": 0, "under": 0}
    pace: dict[str, Tally] = {}
    blocks: dict[str, Tally] = {}
    hr_n = hr_within = 0

    for day, session, family, act in sessions:

        if act is None and day >= today:

            continue                      # a de hoje ainda pode sair

        prescribed += 1

        if act is None:

            continue

        done += 1

        km, minutes = session.planned_distance_km, session.planned_duration_minutes

        error = None

        if km:

            error = (act.distance or 0) / 1000 / km - 1

        elif minutes and act.moving_time:

            error = act.moving_time / 60 / minutes - 1

        if error is not None:

            dist["n"] += 1

            if error > DIST_TOLERANCE:

                dist["over"] += 1

            elif error < -DIST_TOLERANCE:

                dist["under"] += 1

            else:

                dist["within"] += 1

        pace_s = act.moving_time / (act.distance / 1000) if act.distance else None

        _, comparable = ExecutionLog._session_target(session, family)

        if comparable and family in _PACE_FAMILIES:

            gap = _gap(pace_s, comparable)

            if gap is not None:

                pace.setdefault(family, Tally(family)).add(gap)

        heart_rate = getattr(act, "average_heartrate", None)

        if family in _HR_FAMILIES and heart_rate and ceiling:

            hr_n += 1

            hr_within += heart_rate <= ceiling

        if family in _NO_BLOCK_STATS:

            continue

        entry = ExecutionLog._entry_for(act, log)

        for block in (entry or {}).get("blocks", []):

            if not block.get("target") or not block.get("pace"):

                continue

            gap = _gap(_sec(block["pace"]), block["target"])

            if gap is not None:

                blocks.setdefault(family, Tally(family)).add(gap)

    if not prescribed:

        return None

    volume = []

    for plan in plans:

        end = plan.week_start + timedelta(days=6)

        if end > today or plan.week_start < today - timedelta(weeks=weeks) or not plan.weekly_volume:

            continue

        km_done = sum(
            (a.distance or 0) / 1000 for a in activities
            if plan.week_start <= TrainingPatterns._local_day(a.start_date) <= end
        )

        volume.append((plan.week_start, float(plan.weekly_volume), round(km_done, 1)))

    return Scoreboard(
        weeks=weeks,
        prescribed=prescribed,
        done=done,
        dist_n=dist["n"], dist_within=dist["within"], dist_over=dist["over"],
        dist_under=dist["under"],
        pace=[t for t in pace.values() if t.n >= MIN_N],
        hr_n=hr_n, hr_within=hr_within, ceiling=ceiling,
        blocks=[t for t in blocks.values() if t.n >= _MIN_BLOCKS],
        volume=sorted(volume),
    )


def _side(values: list[int], word: str) -> str:

    if not values:

        return ""

    return f"{len(values)} {word} (mediana {median(values):.0f} s/km)"


def _tally_text(t: Tally, unit: str, beyond: str) -> str:

    parts = [f"{t.inside} {'na faixa' if unit == 'corridas' else 'no alvo'}"]

    for values, word in ((t.faster, "mais rápidas"), (t.slower, "mais lentas")):

        if values:

            parts.append(_side(values, word))

    return f"de {t.n} {unit}: " + "; ".join(parts) + beyond


def render(board: Scoreboard | None) -> str:
    """O bloco pro prompt. Vazio sem amostra que fale."""

    if board is None:

        return ""

    lines = []

    if board.prescribed >= MIN_N:

        lines.append(
            f"- Entrega: fez {board.done} de {board.prescribed} sessões prescritas "
            f"({100 * board.done / board.prescribed:.0f}%)."
        )

    if board.dist_n >= MIN_N:

        lines.append(
            f"- Distância: {board.dist_within} de {board.dist_n} sessões ficaram a ±10% do "
            f"prescrito; {board.dist_over} acima e {board.dist_under} abaixo."
        )

    for tally in board.pace:

        lines.append(
            f"- {tally.label} (pace médio da corrida contra a faixa que você deu): "
            + _tally_text(tally, "corridas", " — mais rápida/lenta = além da ponta da faixa.")
        )

    if board.hr_n >= MIN_N and board.ceiling:

        lines.append(
            f"- FC média dentro do teto aeróbico ({board.ceiling} bpm) em {board.hr_within} de "
            f"{board.hr_n} leves/longões."
        )

    for tally in board.blocks:

        lines.append(
            f"- {tally.label} (voltas do relógio contra o alvo): "
            + _tally_text(tally, "voltas", ".")
        )

    if len(board.volume) >= MIN_N:

        errors = [abs(done - plan) / plan for _, plan, done in board.volume if plan]

        lines.append(
            "- Volume semanal (prescrito → feito, km): "
            + ", ".join(f"{week:%d/%m} {plan:.0f}→{done:.0f}" for week, plan, done in board.volume[-6:])
            + f"; erro mediano {100 * median(errors):.0f}%."
        )

    if not lines:

        return ""

    return (
        f"PLACAR DA PRESCRIÇÃO COM ELE (últimas {board.weeks} semanas — o que VOCÊ prescreveu × o "
        "que ele entregou; fato, não ordem):\n"
        + "\n".join(lines)
        + "\nCONHECIMENTO, não regra: um desvio sempre pro MESMO lado, em várias semanas e "
        "com a FC/esforço dentro do que ele aguenta, costuma ser viés da prescrição (o alvo está "
        "acima ou abaixo do que ele faz); um desvio que troca de lado, ou aparece numa semana só, é "
        "variação do dia (calor, sono, gripe, chuva, agenda) e não mexe no plano dele. Pese isso com "
        "o contexto que ele contou e decida: ajustar o alvo, a dose ou nada."
    )
