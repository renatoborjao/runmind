"""A ADAPTAÇÃO DO ATLETA — o que pesa MAIS que um sinal curto de corpo.

O coach cortava o plano do Leonardo (29/10: 23,5 → 15 km, longão de 9-10 → 6 km) porque o corpo deu
sinal por 2 dias (acidente de moto, sono curto) e a carga aguda/crônica passou de 1,4 — razão que
o PRÓPRIO plano criou ao saltar de 12 pra 22 km. Só que o histórico dele diz outra coisa: cumpriu
100% do plano nas três últimas semanas, estava "absorvendo bem" nas duas semanas de 22 km, e as
duas vezes que o corpo deu sinal (28/09, 12/10) voltou ao normal na semana seguinte. O dono (Renato,
29/10): "problemas acontecem; o que de fato segue e deve considerar é a evolução e adaptação do
atleta" — uma semana ruim não decide o plano.

Aqui sai o retrato dessa adaptação: o cumprimento recente, como o corpo estava nas semanas mais
pesadas dele e quantos sinais de corpo ele já deu e se voltou ao normal na semana seguinte (a
economia aeróbica fica na leitura oficial da Forma, uma verdade só). É DADO + CONHECIMENTO pro
coach ([[feedback_ia_decide_sem_regras]]): o tamanho do recuo acompanha o sinal e a adaptação, e a
decisão é dele. Puro/determinístico."""

from dataclasses import dataclass
from datetime import date

from app.application.history.weekly_evolution_digest import _BODY_PT, WeekStat

# estados do corpo que são SINAL (o resto = normal: absorvendo, equilibrado, descansado, montando)
_FLAGGED = {"STRAINED", "RECOVERY_FLAG"}

# semana pesada dele = a partir desta fração da maior semana fechada da janela
_HEAVY_SHARE = 0.85

# cumprimento do plano (sessões feitas ÷ prescritas) a partir do qual "ele cumpre"
_CUMPRE = 0.85

# dos sinais que ele já deu, a fração que voltou ao normal na semana seguinte pra "ele se recupera
# rápido"
_RECOVERS = 0.6


@dataclass(slots=True)
class Adaptation:

    fulfilled: int
    planned: int
    heavy: list[tuple[date, float, str | None]]      # (semana, km, estado do corpo nela)
    dips: list[tuple[date, bool]]                    # (semana do sinal, voltou ao normal depois?)

    @property
    def complies(self) -> bool:

        return self.planned == 0 or self.fulfilled >= _CUMPRE * self.planned

    @property
    def recovered(self) -> int:

        return sum(1 for _, back in self.dips if back)

    @property
    def recovers_fast(self) -> bool:
        """Dos sinais que já deu, voltou ao normal na semana seguinte na maioria. Sem sinais
        anteriores não há o que provar: não conta contra nem a favor."""

        return not self.dips or self.recovered >= _RECOVERS * len(self.dips)

    @property
    def adapts(self) -> bool:
        """Cumpre o plano e se recupera rápido — o sinal curto de agora tende a ser passageiro."""

        return self.complies and self.recovers_fast


def _is_flagged(week: WeekStat) -> bool:

    return week.body is not None and week.body.body_state in _FLAGGED


def assess(
    stats: list[WeekStat], fulfilled: int, planned: int, current: date,
) -> Adaptation | None:
    """O retrato da adaptação a partir das semanas (a mais antiga primeiro; `current` = a semana em
    andamento, que não entra) e do cumprimento recente. None sem semana fechada com corrida."""

    closed = [w for w in stats if w.start < current]

    ran = [w for w in closed if w.runs]

    if not ran:

        return None

    top = max(w.km for w in ran)

    heavy = [
        (w.start, w.km, w.body.body_state if w.body else None)
        for w in ran if top > 0 and w.km >= _HEAVY_SHARE * top
    ]

    dips = []

    for index, week in enumerate(stats):

        if week.start >= current or not _is_flagged(week):

            continue

        later = stats[index + 1] if index + 1 < len(stats) else None

        if later is None or later.body is None:

            continue

        dips.append((week.start, not _is_flagged(later)))

    return Adaptation(fulfilled, planned, heavy, dips)


def _day(day: date) -> str:

    return f"{day:%d/%m}"


def render(found: Adaptation, *, directive: bool = False) -> str:
    """O bloco do dossiê. `directive` (só a voz do plano) acrescenta como pesar o que ele mostra."""

    lines = [
        "ADAPTAÇÃO DELE (o histórico que pesa MAIS que um sinal curto de corpo de poucos dias):"
    ]

    if found.planned:

        lines.append(
            f"- Cumpriu {found.fulfilled} de {found.planned} sessões do plano nas últimas "
            "semanas fechadas."
        )

    if found.heavy:

        shown = ", ".join(
            f"{_day(day)} ({km:.0f} km, corpo {_BODY_PT.get(state, state.lower())})"
            if state else f"{_day(day)} ({km:.0f} km)"
            for day, km, state in found.heavy
        )

        fine = sum(1 for _, _, state in found.heavy if state and state not in _FLAGGED)

        with_body = sum(1 for _, _, state in found.heavy if state)

        tail = (
            f" — em {fine} de {with_body} o corpo não deu sinal na própria semana"
            if with_body else ""
        )

        lines.append(f"- Semanas mais pesadas dele: {shown}{tail}.")

    if found.dips:

        weeks = ", ".join(_day(day) for day, _ in found.dips)

        lines.append(
            f"- Sinais de corpo anteriores (semanas de {weeks}): voltou ao normal na semana "
            f"seguinte em {found.recovered} de {len(found.dips)}."
        )

    if directive:

        lines.append(_knowledge(found))

    return "\n".join(lines)


def _knowledge(found: Adaptation) -> str:

    if found.adapts:

        return (
            "CONHECIMENTO, não regra: a evolução e a adaptação dele pesam MAIS que a semana ruim. "
            "Um sinal de corpo de poucos dias, num atleta que cumpre o plano e costuma voltar ao "
            "normal em cerca de uma semana, tende a ser passageiro — a resposta proporcional é "
            "SEGURAR a rampa (não subir) ou recuar LEVE (≈10-20%), mantendo os dias e o longão "
            "perto do que ele já correu; corte fundo (30% ou mais) fica pra dor, doença, sinal que "
            "persiste por semanas ou desempenho piorando. Recuo fundo seguido de volta ao volume "
            "cheio é dente de serra: o corpo dele responde melhor a degraus do que a vales."
        )

    reasons = []

    if not found.complies:

        reasons.append("ele cumpre pouco do plano")

    if not found.recovers_fast:

        reasons.append("os sinais anteriores NÃO voltaram ao normal na semana seguinte")

    return (
        f"CONHECIMENTO, não regra: aqui o histórico dele pede mais peso ao sinal de corpo "
        f"({'; '.join(reasons)}). Um recuo maior é coerente — mas proporcional, e ancorado no que "
        "ele de fato cumpre."
    )


__all__ = ["Adaptation", "assess", "render"]
