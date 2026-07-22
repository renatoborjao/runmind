from dataclasses import dataclass, field

# Faixas do ACWR (razão carga aguda:crônica) — o consenso prático do
# "sweet spot". Fora dele, sinal (não diagnóstico): abaixo de 0.8 a forma
# está caindo (destreino); acima de 1.3 a carga subiu rápido demais (risco de
# lesão/overtraining sobe), 1.5+ é alerta forte.
ACWR_DETRAINING = 0.8
ACWR_OPTIMAL_MAX = 1.3
ACWR_CAUTION_MAX = 1.5

# status possíveis (string, não enum, pra casar com o estilo do projeto)
LOAD_INSUFFICIENT = "INSUFFICIENT_DATA"
LOAD_DETRAINING = "DETRAINING"
LOAD_OPTIMAL = "OPTIMAL"
LOAD_CAUTION = "CAUTION"
LOAD_HIGH = "HIGH"


@dataclass(slots=True)
class TrainingLoad:
    """Retrato da CARGA de treino do atleta num momento — a base do radar de
    sobrecarga (camada 2). Carga = minutos de treino (duração); janela aguda
    (7 dias) vs crônica (média semanal dos últimos 28 dias); o ACWR é a razão
    entre as duas.

    v1 é por DURAÇÃO (não pondera intensidade) — honesto e funciona em
    qualquer fonte, mas um tiro curto e forte pesa igual a um trote longo.
    Ponderar por FC (TRIMP) é o refinamento previsto pra v2 (já temos FC média
    por treino e FC de repouso). Não é diagnóstico médico — é sinal de coach.
    """

    acute_load: float          # carga dos últimos 7 dias (min)
    chronic_load: float        # carga média SEMANAL dos últimos 28 dias (min)
    acwr: float | None         # aguda/crônica; None quando não dá pra calcular
    status: str                # LOAD_* acima
    days_of_history: int       # dias entre o treino mais antigo e a referência
    weekly_loads: list[float] = field(default_factory=list)  # 4 sem, antigo→novo
