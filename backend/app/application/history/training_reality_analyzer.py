"""REALIDADE × PLANO: o atleta treina o que o coach prescreve, ou vive por conta
própria? O `preferred_running_days` é o que ele REGISTROU (rígido); o que ele
FAZ de verdade pode divergir — o Hélio registrou 3 dias e faz 4x na maioria das
semanas. Sem ler isso, o coach subestima o volume de quem faz MAIS (plano
descola) ou insiste com quem faz MENOS (plano que ele nunca cumpre).

REGRA (Renato): uma semana isolada NÃO é nada — só quando o comportamento é
ROTINA (se repete na maioria das últimas semanas) é que conta. E o coach nunca
muda a FREQUÊNCIA sozinho: o plano só garante o piso de VOLUME nos dias
registrados; oficializar mais um dia é uma CONVERSA (o atleta decide).

Puro/determinístico: conta as corridas reais por semana. Não fala com o atleta.
Ver [[feedback_tudo_dinamico]], [[feedback_base_historico_sempre]] e
[[project_track_a_plano_fiel]]."""

from collections import Counter
from dataclasses import dataclass
from statistics import mean

from app.application.history.weekly_buckets import activity_date, group_by_week

_WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday",
]

# as últimas N semanas ATIVAS definem a "rotina"; precisa de N pra afirmar
# (menos que isso, não dá pra separar rotina de uma fase pontual)
_WINDOW = 4

# em quantas dessas semanas o comportamento precisa aparecer pra ser ROTINA
# (3 de 4 = maioria forte; um pico isolado — o 6 do Maurício — não dispara)
_ROUTINE = 3

OVER, UNDER, ALIGNED = "over", "under", "aligned"


@dataclass(slots=True)
class RealityVerdict:

    verdict: str            # over | under | aligned
    registered_days: int
    real_runs_per_week: float
    real_weekly_km: float
    weeks_over: int
    window: int


class TrainingRealityAnalyzer:

    @staticmethod
    def assess(registered_days: int, activities: list) -> RealityVerdict:
        """Conta as corridas por SEMANA nas últimas `_WINDOW` semanas ativas e
        decide se o atleta rotineiramente faz MAIS (ou MENOS) que os dias
        registrados. Sem semanas suficientes, nada a afirmar (aligned)."""

        reg = int(registered_days or 0)

        buckets = group_by_week(activities or [])

        recent = sorted(buckets)[-_WINDOW:]

        empty = RealityVerdict(ALIGNED, reg, 0.0, 0.0, 0, len(recent))

        if reg <= 0 or len(recent) < _WINDOW:

            return empty

        counts = [len(buckets[k]) for k in recent]

        kms = [
            sum(a.distance for a in buckets[k]) / 1000 for k in recent
        ]

        over = sum(1 for c in counts if c > reg)

        under = sum(1 for c in counts if c < reg)

        avg_runs = round(mean(counts), 1)

        avg_km = round(mean(kms))

        if over >= _ROUTINE:

            return RealityVerdict(OVER, reg, avg_runs, avg_km, over, len(recent))

        if under >= _ROUTINE:

            return RealityVerdict(UNDER, reg, avg_runs, avg_km, under, len(recent))

        return RealityVerdict(ALIGNED, reg, avg_runs, avg_km, over, len(recent))

    @staticmethod
    def extra_weekday(registered_weekdays: list[str], activities: list):
        """O dia da semana (nome em inglês) que ele mais corre FORA dos
        registrados, nas últimas semanas ativas — o dia a oficializar quando ele
        topa. None se não há um extra claro."""

        registered = {d for d in registered_weekdays or []}

        buckets = group_by_week(activities or [])

        recent = sorted(buckets)[-_WINDOW:]

        counts: Counter = Counter()

        for key in recent:

            for activity in buckets[key]:

                try:

                    name = _WEEKDAY_NAMES[activity_date(activity).weekday()]

                except (ValueError, TypeError):

                    continue

                if name not in registered:

                    counts[name] += 1

        return counts.most_common(1)[0][0] if counts else None


def training_reality_directive(verdict: RealityVerdict) -> str:
    """Diretriz COACH-facing pro plano. NÃO manda mudar a frequência (isso é
    conversa com o atleta); só garante o piso de VOLUME nos dias registrados.
    Vazio quando plano e realidade já batem."""

    if verdict.verdict == OVER:

        return (
            f"REALIDADE × PLANO: ele registrou {verdict.registered_days} dias, "
            f"mas vem correndo ~{verdict.real_runs_per_week:.0f}x "
            f"(~{verdict.real_weekly_km:.0f} km) de verdade na MAIORIA das "
            "últimas semanas — treina além do plano de forma consistente. NÃO o "
            f"subestime: prescreva o volume à altura do que ele já faz "
            f"(~{verdict.real_weekly_km:.0f} km), distribuído nos "
            f"{verdict.registered_days} dias registrados (sessões mais "
            "completas). NÃO adicione dias por conta própria — a frequência é "
            "escolha dele; o piso é o volume real."
        )

    if verdict.verdict == UNDER:

        return (
            f"REALIDADE × PLANO: ele registrou {verdict.registered_days} dias, "
            f"mas só vem sustentando ~{verdict.real_runs_per_week:.0f}x "
            f"(~{verdict.real_weekly_km:.0f} km) na maioria das últimas semanas. "
            "Ancore no que ele REALMENTE cumpre em vez de forçar dias que ele "
            "fura — um plano que ele fecha vale mais que um cheio que o frustra."
        )

    return ""


def frequency_reconcile_message(
    runner_name: str, verdict: RealityVerdict, weekday_label: str | None = None
) -> str:
    """A pergunta ATHLETE-facing do coach quando ele vem treinando ALÉM dos dias
    registrados de forma rotineira: quer oficializar mais um dia? Orientar, não
    mandar — o atleta decide. Vazia quando não é 'over'. `weekday_label` (em
    pt) cita o dia que ele mais adiciona."""

    if verdict.verdict != OVER:

        return ""

    real = round(verdict.real_runs_per_week)

    reg = verdict.registered_days

    dia = f" — geralmente {weekday_label}" if weekday_label else ""

    com_dia = f" (fixando o {weekday_label})" if weekday_label else ""

    return (
        f"{runner_name}, reparei que você vem metendo um treino a mais além dos "
        f"{reg} do teu plano{dia}, já faz umas semanas ({real}x por semana na "
        f"real). 👊 Quer que eu passe teu plano pra {real} dias/semana{com_dia}? "
        "Aí eu monto já contando com ele e distribuo melhor a carga, em vez de "
        f"você somar por fora. Se preferir manter os {reg} e o extra ficar "
        "livre, também tá ótimo — é só dizer."
    )
