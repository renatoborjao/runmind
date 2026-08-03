"""Alerta PRECOCE de risco de lesão: soma os fatores de risco modificáveis num
veredito, ANTES de virar lesão. Puro/determinístico, sinal de coach (não
diagnóstico médico). Fatores (consenso prático de carga:lesão):

- SPIKE de carga (ACWR alto) — o preditor nº1 modificável; >1.5 é alerta forte.
- RAMPA de volume — semana pulou muito acima da anterior (regra dos ~10%).
- RECUPERAÇÃO caindo — HRV/FC-repouso piorando (corpo não acompanha a carga).
- HISTÓRICO de lesão — quem já lesionou tem risco de base maior no mesmo spike.

Ver [[project_ideias_produto]] item 27 e [[project_analise_corpo_garmin]]."""

from app.domain.entities.body_reading import FALLING, RecoveryTrend
from app.domain.entities.injury_risk import (
    RISK_ELEVATED,
    RISK_HIGH,
    RISK_LOW,
    InjuryRisk,
)
from app.domain.entities.training_load import (
    ACWR_CAUTION_MAX,
    ACWR_OPTIMAL_MAX,
    TrainingLoad,
)

# salto de carga semana-a-semana que já é "rampa rápida demais" (bem além dos
# ~10%/semana recomendados)
_RAMP_JUMP = 1.5  # última semana ≥ 1.5× a anterior

# pontuação → nível
_HIGH_AT = 3
_ELEVATED_AT = 2


class InjuryRiskAnalyzer:

    @staticmethod
    def assess(
        load: TrainingLoad,
        recovery: RecoveryTrend,
        injuries: list[str] | None = None,
        form_fading: bool = False,
    ) -> InjuryRisk:

        points = 0

        reasons: list[str] = []

        # FORMA quebrando sob fadiga (cadência desabando no fim das corridas) —
        # o atleta arrasta/aterrissa desleixado quando cansa; risco sobe
        if form_fading:

            points += 1

            reasons.append("forma quebrando sob fadiga (cadência caindo no fim)")

        # SPIKE de carga (ACWR)
        if load.acwr is not None:

            if load.acwr > ACWR_CAUTION_MAX:

                points += 2

                reasons.append(
                    f"carga subiu rápido demais (ACWR {load.acwr:.1f})"
                )

            elif load.acwr > ACWR_OPTIMAL_MAX:

                points += 1

                reasons.append(f"carga na faixa de atenção (ACWR {load.acwr:.1f})")

        # RAMPA de volume (última semana muito acima da anterior)
        if InjuryRiskAnalyzer._ramped(load.weekly_loads):

            points += 1

            reasons.append("volume pulou muito de uma semana pra outra")

        # RECUPERAÇÃO caindo
        if recovery.hrv_direction == FALLING or recovery.rhr_direction == FALLING:

            points += 1

            reasons.append("recuperação vem caindo (HRV/FC-repouso)")

        # HISTÓRICO de lesão — risco de base maior no mesmo spike
        if injuries:

            points += 1

            reasons.append("histórico de lesão")

        return InjuryRisk(
            level=InjuryRiskAnalyzer._level(points),
            reasons=reasons,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _ramped(weekly_loads: list[float]) -> bool:
        """Última semana saltou ≥ _RAMP_JUMP× a anterior (rampa perigosa). Só
        com pelo menos 2 semanas e uma base anterior não-trivial."""

        if len(weekly_loads) < 2:

            return False

        prev, last = weekly_loads[-2], weekly_loads[-1]

        return prev > 0 and last >= prev * _RAMP_JUMP

    @staticmethod
    def _level(points: int) -> str:

        if points >= _HIGH_AT:

            return RISK_HIGH

        if points >= _ELEVATED_AT:

            return RISK_ELEVATED

        return RISK_LOW


def injury_risk_directive(risk: InjuryRisk) -> str:
    """Diretriz COACH-facing pro plano: quando o risco sobe, o coach constrói
    uma semana mais segura (segura a rampa, prioriza base/recuperação). Vazio
    em risco baixo — sem ruído no prompt."""

    if not risk.elevated:

        return ""

    label = "ALTO" if risk.level == RISK_HIGH else "ELEVADO"

    return (
        f"RISCO DE LESÃO {label} ({'; '.join(risk.reasons)}). Prevenção: "
        "NÃO suba volume nem empilhe qualidade esta semana — segure a rampa, "
        "priorize base/recuperação e um dia leve a mais. É sinal de coach, "
        "não diagnóstico."
    )


def injury_risk_chat_line(risk: InjuryRisk) -> str:
    """Linha compacta pro quadro do coach de conversa. Vazio em risco baixo."""

    if not risk.elevated:

        return ""

    label = "alto" if risk.level == RISK_HIGH else "elevado"

    return (
        f"- Risco de lesão: {label} — {'; '.join(risk.reasons)} "
        "(prevenção: segurar a rampa, não empilhar carga)"
    )
