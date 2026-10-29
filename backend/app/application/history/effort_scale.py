"""A RÉGUA DE ESFORÇO DO ATLETA — o que o número que ele diz sentir significa PRA ELE.

O esforço percebido (0-10) entrava no coach como número absoluto: "≤3/10" era treino leve, "5+" era
forte. Só que cada atleta usa a escala do seu jeito (Renato, 29/10: "nem todos usam a medição de
esforço correta"). Medido nos atletas reais:

- Maurício responde 2 ou 3 em 22 de 23 corridas — mas o número ACOMPANHA a intensidade (correlação
  +0,74 com a FC e +0,83 com o ritmo): pra ele 3 já é puxado, e "≤3 = leve" o acusaria à toa.
- Leonardo responde 3 em 73% das vezes e o número NÃO acompanha o ritmo (-0,03) nem a FC (+0,26):
  é um valor-padrão; não diz nada de leve ou forte.
- Fernanda: 1 a 3 e sem relação com a FC (-0,05). Renato: escala larga (3 a 8), acompanha.

Aqui a régua de cada atleta é MEDIDA nos relatos dele contra a intensidade objetiva (FC média e
velocidade da corrida do dia). Número que acompanha a intensidade vale — lido pelo habitual DELE
(posição entre os relatos dele), não pelo absoluto; número que não acompanha, ou ainda sem relatos
pra saber, NÃO é evidência de nada (nem de folga, nem de excesso). Puro/determinístico; o coach
decide o que fazer com isso ([[feedback_ia_decide_sem_regras]])."""

from dataclasses import dataclass
from math import sqrt
from statistics import median

# relatos (e pares relato × corrida) mínimos pra dizer se o número dele acompanha o treino
MIN_REPORTS = 8
MIN_PAIRS = 8

# o número "acompanha" quando a correlação de postos com a intensidade é positiva e passa de ~95%
# (unilateral): rho × raiz(pares − 1) ≥ Z
_Z = 1.645

# posição do número entre os relatos dele: até aqui = dos mais leves; daqui pra cima = dos mais
# puxados; no meio = o habitual
LOW_RANK = 0.3
HIGH_RANK = 0.7

# só corridas de verdade entram na comparação com a intensidade
_MIN_RUN_M = 2000

READS = "acompanha"
FLAT = "nao_acompanha"
FEW = "poucos_relatos"

LOW = "baixo"
USUAL = "habitual"
HIGH = "puxado"


@dataclass(slots=True, frozen=True)
class EffortScale:

    reports: tuple[int, ...] = ()
    rho: float | None = None
    pairs: int = 0
    kind: str = FEW

    @property
    def reads(self) -> bool:
        """O número dele acompanha o treino: dá pra ler como evidência (pelo habitual dele)."""

        return self.kind == READS

    @property
    def median(self) -> float | None:

        return median(self.reports) if self.reports else None

    def rank(self, rpe: int | None) -> float | None:
        """Posição do número entre os relatos dele (0 = o mais leve que ele relata, 1 = o mais
        puxado). None sem relatos."""

        if rpe is None or not self.reports:

            return None

        below = sum(1 for r in self.reports if r < rpe)

        equal = sum(1 for r in self.reports if r == rpe)

        return (below + 0.5 * equal) / len(self.reports)

    def level(self, rpe: int | None) -> str | None:
        """Leve / habitual / puxado PRA ELE. None quando o número dele não acompanha o treino (não
        é evidência) ou não há relato."""

        if not self.reads:

            return None

        rank = self.rank(rpe)

        if rank is None:

            return None

        if rank <= LOW_RANK:

            return LOW

        return HIGH if rank >= HIGH_RANK else USUAL

    def high_from(self) -> int | None:
        """O menor valor que já é puxado pra ele."""

        for value in sorted(set(self.reports)):

            if self.level(value) == HIGH:

                return value

        return None

    def below_habit(self, recent: list[int]) -> bool:
        """Os relatos recentes estão abaixo do habitual DELE (não do absoluto). Falso quando o
        número dele não acompanha o treino."""

        if not self.reads or len(recent) < 3:

            return False

        return median(recent) <= self.median - 1


UNKNOWN = EffortScale()


# --- correlação de postos --------------------------------------------------------------------


def _ranks(values: list[float]) -> list[float]:

    order = sorted(range(len(values)), key=lambda i: values[i])

    out = [0.0] * len(values)

    i = 0

    while i < len(order):

        j = i

        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:

            j += 1

        for k in range(i, j + 1):

            out[order[k]] = (i + j) / 2 + 1

        i = j + 1

    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Correlação de postos (Spearman) com empates. None com menos de 3 pontos ou sem variação."""

    if len(xs) < 3 or len(xs) != len(ys):

        return None

    rx, ry = _ranks(xs), _ranks(ys)

    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)

    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))

    den = sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))

    return num / den if den else None


# --- a régua ---------------------------------------------------------------------------------


def _pairs(rows: list[tuple[str, int]], activities) -> tuple[list, list]:
    """(esforço, FC média ÷ FC máx dele) e (esforço, velocidade ÷ mediana dele) da corrida de cada
    dia com relato — a intensidade objetiva contra a qual o número é conferido."""

    from app.application.history.weekly_buckets import activity_date
    from app.domain.value_objects.sports import is_foot_sport

    runs = [
        a for a in activities or []
        if is_foot_sport(getattr(a, "sport", None))
        and (getattr(a, "distance", 0) or 0) >= _MIN_RUN_M
    ]

    if not runs:

        return [], []

    hr_max = max((getattr(a, "max_heartrate", None) or 0 for a in runs), default=0)

    speeds = [a.average_speed for a in runs if getattr(a, "average_speed", None)]

    typical = median(speeds) if speeds else None

    by_day: dict[str, object] = {}

    for a in runs:

        key = activity_date(a).isoformat()

        if key not in by_day or a.distance > by_day[key].distance:

            by_day[key] = a

    hr_pairs, pace_pairs = [], []

    for day, rpe in rows:

        act = by_day.get(day)

        if act is None:

            continue

        if getattr(act, "average_heartrate", None) and hr_max:

            hr_pairs.append((rpe, act.average_heartrate / hr_max))

        if getattr(act, "average_speed", None) and typical:

            pace_pairs.append((rpe, act.average_speed / typical))

    return hr_pairs, pace_pairs


def build(sessions, activities) -> EffortScale:
    """A régua dele a partir dos relatos (`SessionRpe`) e das corridas."""

    rows = sorted(
        (str(s.day), int(s.rpe)) for s in sessions or [] if getattr(s, "rpe", None) is not None
    )

    reports = tuple(r for _, r in rows)

    if len(reports) < MIN_REPORTS:

        return EffortScale(reports=reports, kind=FEW)

    # a melhor das duas conferências (FC ou ritmo): quem não tem relógio de FC ainda é conferido
    # pelo ritmo, e vice-versa
    best = None

    for pairs in _pairs(rows, activities):

        if len(pairs) < MIN_PAIRS:

            continue

        # sem variação nos relatos (responde sempre o mesmo) a correlação não existe: o número não
        # acompanha nada
        rho = spearman([p[0] for p in pairs], [p[1] for p in pairs]) or 0.0

        z = rho * sqrt(len(pairs) - 1)

        if best is None or z > best[0]:

            best = (z, rho, len(pairs))

    if best is None:

        return EffortScale(reports=reports, kind=FEW)

    z, rho, pairs = best

    return EffortScale(reports=reports, rho=rho, pairs=pairs, kind=READS if z >= _Z else FLAT)


def for_data(profile: str, activities) -> EffortScale:
    """A régua a partir do storage dos relatos + as corridas já carregadas. Best-effort: qualquer
    falha = régua desconhecida (o número dele não vira evidência)."""

    try:

        from app.infrastructure.persistence.session_rpe_repository import SessionRpeRepository

        return build(SessionRpeRepository().load_sessions(profile), activities)

    except Exception as e:  # noqa: BLE001

        print(f"Régua de esforço falhou p/ '{profile}': {e}")

        return UNKNOWN


# --- o que o coach lê ------------------------------------------------------------------------


def note(scale: EffortScale) -> str:
    """Como ler o esforço que ELE relata — pro dossiê de todas as vozes. Vazio sem relato."""

    if not scale.reports:

        return ""

    low, high = min(scale.reports), max(scale.reports)

    if scale.kind == FEW:

        return (
            f"COMO LER O ESFORÇO DELE: ainda são poucos relatos ({len(scale.reports)}) pra saber "
            "se o número dele acompanha o treino — não conclua folga nem excesso só por ele."
        )

    rho = f"{scale.rho:+.1f}"

    if scale.kind == FLAT:

        mode = max(set(scale.reports), key=scale.reports.count)

        share = scale.reports.count(mode) / len(scale.reports)

        return (
            "COMO LER O ESFORÇO DELE: o número que ele relata NÃO acompanha o ritmo nem a FC "
            f"(correlação {rho}; {share:.0%} das respostas são {mode}/10). Não use como medida de "
            "intensidade nem como sinal de folga (\"esforço baixo\") ou de excesso — decida por "
            "ritmo, FC e blocos medidos, e ensine a escala quando a conversa abrir espaço."
        )

    start = scale.high_from()

    usual = f"{scale.median:g}"

    if high - low <= 2:

        return (
            f"COMO LER O ESFORÇO DELE: ele usa só uma faixa estreita da escala ({low} a {high}, "
            f"o habitual é {usual}), mas o número acompanha o ritmo e a FC (correlação {rho}). "
            f"Leia pelo habitual DELE: {start} ou mais é puxado pra ele; baixo em absoluto não é "
            "leve pra ele."
        )

    return (
        f"COMO LER O ESFORÇO DELE: o número acompanha o ritmo e a FC (correlação {rho}); a escala "
        f"dele vai de {low} a {high} e o habitual é {usual}"
        + (f" ({start}+ é puxado pra ele)" if start else "")
        + ". Pese em relação ao habitual dele."
    )


def describe(rpe: int | None, scale: EffortScale) -> str:
    """O número dele lido pela régua dele (pra frase de uma sessão). Vazio quando o número não é
    evidência."""

    level = scale.level(rpe)

    return {
        LOW: "dos mais leves que ele relata",
        USUAL: "o habitual dele",
        HIGH: "dos mais puxados que ele relata",
    }.get(level, "")
