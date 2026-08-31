"""REALIDADE × PLANO: o atleta treina o que o coach prescreve, ou vive por conta
própria? O `preferred_running_days` é o que ele REGISTROU (rígido); o que ele
FAZ de verdade (frequência/volume reais, do histórico) pode ser bem diferente —
o Hélio registrou 3 dias e corre ~5x/~28 km. Sem ler isso, o coach subestima
quem faz MAIS (plano descola da realidade) ou insiste com quem faz MENOS (plano
que ele nunca cumpre).

Puro/determinístico: recebe o baseline (já traz `runs_per_week` e `weekly_km`
reais) + os dias registrados, e vira uma diretriz pra o gerador dimensionar o
plano à VERDADE. Não fala com o atleta nem decide sozinho. Ver
[[feedback_tudo_dinamico]], [[feedback_base_historico_sempre]] e
[[project_track_a_plano_fiel]]."""

from dataclasses import dataclass

from app.domain.entities.runner_baseline import RunnerBaseline

# corre pelo menos 1 dia A MAIS (ou A MENOS) que o registrado, de forma
# sustentada (o runs_per_week já é média de 4 semanas ativas) -> descolamento
_FREQ_GAP = 1.0

# margem do volume: só cita "faz mais km" quando é claramente acima (evita
# ruído de uma semana forte)
_KM_OVER_RATIO = 1.20

OVER, UNDER, ALIGNED = "over", "under", "aligned"


@dataclass(slots=True)
class RealityVerdict:

    verdict: str            # over | under | aligned
    registered_days: int
    real_runs_per_week: float
    real_weekly_km: float


class TrainingRealityAnalyzer:

    @staticmethod
    def assess(
        registered_days: int, baseline: RunnerBaseline
    ) -> RealityVerdict:
        """Compara a frequência REAL (baseline) com os dias REGISTRADOS. Só
        afirma com histórico real (Strava) — sem lastro, nada a dizer."""

        real = round(baseline.runs_per_week or 0.0, 1)

        reg = int(registered_days or 0)

        aligned = RealityVerdict(ALIGNED, reg, real, baseline.weekly_km)

        # sem histórico real (só declarado) ou sem dias registrados: não afirma
        if not baseline.has_history or reg <= 0 or real <= 0:

            return aligned

        if real >= reg + _FREQ_GAP:

            return RealityVerdict(OVER, reg, real, baseline.weekly_km)

        if real <= reg - _FREQ_GAP:

            return RealityVerdict(UNDER, reg, real, baseline.weekly_km)

        return aligned


def training_reality_directive(verdict: RealityVerdict) -> str:
    """Diretriz COACH-facing pro plano: dimensione à realidade do atleta.
    Vazio quando plano e realidade já batem — sem ruído."""

    if verdict.verdict == OVER:

        return (
            f"REALIDADE × PLANO (dimensione à VERDADE dele): ele registrou "
            f"{verdict.registered_days} dias/semana, mas vem CORRENDO "
            f"~{verdict.real_runs_per_week:.0f}x (~{verdict.real_weekly_km:.0f} "
            "km) de verdade nas últimas semanas — treina por conta além do "
            "plano. NÃO o subestime devolvendo menos do que ele já faz sozinho: "
            f"dimensione o plano pra ~{verdict.real_runs_per_week:.0f} dias e o "
            "volume à altura do que ele sustenta, com progressão segura e a "
            "variação de estímulo da fase/meta. Se fizer sentido manter os dias "
            "registrados, ao menos distribua o volume REAL neles — nunca um "
            "plano abaixo do que ele treina."
        )

    if verdict.verdict == UNDER:

        return (
            f"REALIDADE × PLANO: ele registrou {verdict.registered_days} dias, "
            f"mas só vem sustentando ~{verdict.real_runs_per_week:.0f}x "
            f"(~{verdict.real_weekly_km:.0f} km) nas últimas semanas. Ancore no "
            "que ele REALMENTE cumpre em vez de forçar dias que ele fura — um "
            "plano que ele fecha vale mais que um cheio que o frustra."
        )

    return ""
