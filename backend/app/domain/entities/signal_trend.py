from dataclasses import dataclass

# direção de um sinal ao longo do tempo (POV "melhor forma")
TREND_IMPROVING = "IMPROVING"
TREND_STABLE = "STABLE"
TREND_DECLINING = "DECLINING"

# confiança da leitura: CLEAR = mexeu além do ruído E com linearidade razoável;
# MARGINAL = direção sugerida, mas no limite do ruído (poucos pontos/dispersão)
CONF_CLEAR = "CLEAR"
CONF_MARGINAL = "MARGINAL"


@dataclass(slots=True)
class SignalTrend:
    """Tendência de UM sinal de forma (EF, VO₂máx, FC-repouso) numa janela,
    estimada por regressão linear. Genérico e reutilizável — o mesmo primitivo
    serve os três sinais e os dois horizontes (curto/longo).

    `relative_change` é a variação fracionária PROJETADA pela reta ao longo do
    span observado (inclinação × dias ÷ média), já orientada pra "melhora
    positiva" (em FC-repouso, cair é melhorar → o estimador inverte). Ver
    [[TrendEstimator]] e [[project_analise_corpo_garmin]]."""

    direction: str
    confidence: str

    points: int          # nº de amostras que entraram
    span_days: int       # dias entre a 1ª e a última amostra
    span_weeks: int

    relative_change: float   # fração projetada (+ = melhora), já orientada
    per_week: float          # variação por semana na UNIDADE do sinal (cru)
    r_squared: float

    recent_value: float      # valor ajustado pela reta no fim do span
    earlier_value: float     # valor ajustado pela reta no início do span
    mean_value: float

    @property
    def improving(self) -> bool:

        return self.direction == TREND_IMPROVING

    @property
    def clear(self) -> bool:

        return self.confidence == CONF_CLEAR
