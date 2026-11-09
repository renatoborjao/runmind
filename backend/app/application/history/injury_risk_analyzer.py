"""Alerta PRECOCE de risco de lesão: soma os fatores de risco modificáveis num
veredito, ANTES de virar lesão. Puro/determinístico, sinal de coach (não
diagnóstico médico). Fatores (consenso prático de carga:lesão):

- SALTO DE SESSÃO — a maior corrida da semana muito acima da maior dos 30 dias anteriores: é o
  que o estudo com 5 mil corredores (Frandsen et al., BJSM 2025) achou como melhor preditor.
- SPIKE de carga (ACWR alto) e RAMPA de volume (semana pulou) — preditores FRACOS (Impellizzeri
  2020: sem evidência de que a razão sirva pra reduzir lesão; Buist 2008: a regra dos 10% não
  protegeu). Seguem como sinal, mas quando NENHUMA corrida foi um salto de sessão valem no
  máximo 1 ponto juntos: a semana pode ter dobrado só porque ele voltou a 3 corridas.
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

# salto de sessão: até aqui é seguro; acima, risco de lesão por corrida única sobe (10–30% acima da
# maior dos 30 dias já foi 64% mais risco no estudo); o dobro ou mais é de longe o pior
_SAFE_SESSION_SPIKE = 0.10
_HUGE_SESSION_SPIKE = 1.0

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

        # SALTO DE SESSÃO — o preditor mais claro: UMA corrida bem maior que a maior dos últimos
        # 30 dias. É o que a carga tem de mecânico (tendão, osso), e é o que mais pesa aqui.
        session_known = load.long_spike is not None

        session_safe = session_known and load.long_spike <= _SAFE_SESSION_SPIKE

        if session_known and not session_safe:

            big, prev = load.long_run_km or (0.0, 0.0)

            points += 2 if load.long_spike >= _HUGE_SESSION_SPIKE else 1

            reasons.append(
                f"o maior treino da semana ({big:g} km) foi {load.long_spike * 100:.0f}% maior "
                f"que o maior dos 30 dias anteriores ({prev:g} km)"
            )

        # os preditores SEMANAIS (fracos): contam inteiros enquanto não se sabe da sessão, ou
        # quando alguma corrida foi mesmo um salto; sem salto de sessão, no máximo 1 ponto juntos
        weekly_points = 0

        weekly_reasons: list[str] = []

        # SPIKE de carga (ACWR) — em BASE BAIXA sem aumento real de tempo a
        # razão alta não é pico (o analisador da carga já decidiu: low_base)
        if load.acwr is not None and load.low_base is None:

            if load.acwr > ACWR_CAUTION_MAX:

                weekly_points += 2

                weekly_reasons.append(
                    f"carga subiu rápido demais (ACWR {load.acwr:.1f})"
                )

            elif load.acwr > ACWR_OPTIMAL_MAX:

                weekly_points += 1

                weekly_reasons.append(f"carga na faixa de atenção (ACWR {load.acwr:.1f})")

        # RAMPA de volume (última semana muito acima da anterior) — voltar ao que ele sustentava
        # depois de uma semana fraca (chuva, doença) não é rampa: o analisador da carga já decidiu
        # (rebound). Renato 01/11: 46 → 156 min, a semana fraca era a chuva.
        if (
            load.low_base is None
            and load.rebound is None
            and InjuryRiskAnalyzer._ramped(load.weekly_loads)
        ):

            weekly_points += 1

            weekly_reasons.append("volume pulou muito de uma semana pra outra")

        if session_safe and weekly_points > 1:

            weekly_points = 1

        if weekly_reasons:

            points += weekly_points

            reasons.extend(weekly_reasons)

            if session_safe:

                big, prev = load.long_run_km or (0.0, 0.0)

                reasons.append(
                    f"mas nenhuma corrida foi salto: o maior treino ({big:g} km) ficou dentro de "
                    f"10% do maior dos 30 dias anteriores ({prev:g} km)"
                )

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
