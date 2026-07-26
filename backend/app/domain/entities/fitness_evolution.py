from dataclasses import dataclass

from app.domain.entities.aerobic_efficiency import AerobicEfficiency
from app.domain.entities.signal_trend import SignalTrend

# veredito combinado do eixo "estou evoluindo?" (multi-sinal)
EVO_IMPROVING = "IMPROVING"
EVO_STABLE = "STABLE"
EVO_DECLINING = "DECLINING"
EVO_INSUFFICIENT = "INSUFFICIENT"

# confiança do veredito combinado
EVO_CLEAR = "CLEAR"
EVO_MARGINAL = "MARGINAL"
EVO_MIXED = "MIXED"   # sinais discordam (ex.: economia estável, VO₂máx subindo)

# guard de dado velho: sem uma corrida registrada há mais que isto, a leitura
# reflete um momento PASSADO, não o de agora — a forma aeróbica já começa a
# destreinar em ~2-3 semanas paradas. Acima disso, não damos veredito de "agora"
# como se fosse fresco; abstemos e avisamos. Ver [[project_ideias_produto]] #20.
EVO_STALE_AFTER_DAYS = 21


@dataclass(slots=True)
class FitnessEvolution:
    """Veredito ATLETA-FACING do "estou evoluindo?", triangulando os sinais de
    forma que já coletamos, cada um só quando tem lastro:

    - `ef`: eficiência aeróbica (velocidade/FC) na janela curta — o sinal
      sempre-presente (só precisa de pace+FC), com a tradução tangível
      (pace_gain/hr_drop) pra mensagem;
    - `ef_long`: a MESMA economia no horizonte longo (arco de meses) — responde
      "melhorei desde que começamos a acompanhar?";
    - `quality`: economia em ritmo FORTE (faixa de limiar/tiro) — a evolução que
      aparece no treino de qualidade, não só na rodagem;
    - `vo2max`: o número de fitness da PRÓPRIA Garmin (quando o relógio calcula
      e há dias suficientes) — autoritativo quando presente;
    - `rhr`: FC de repouso caindo = adaptação aeróbica (sinal de apoio).

    O `direction`/`confidence` combinam o que estiver disponível: concordância
    entre sinais → CLEAR; divergência → MIXED com nuance. Sem NENHUM sinal com
    lastro → INSUFFICIENT (o chamador cai no fallback). Puro/determinístico —
    o writer só narra. Ver [[TrendEstimator]] e [[project_ideias_produto]]."""

    direction: str = EVO_INSUFFICIENT
    confidence: str = EVO_MARGINAL

    ef: AerobicEfficiency | None = None
    ef_long: SignalTrend | None = None
    quality: SignalTrend | None = None   # economia em ritmo forte (limiar/tiro)
    vo2max: SignalTrend | None = None
    rhr: SignalTrend | None = None

    # dias desde a última corrida registrada (None = nenhuma corrida no
    # histórico). Alimenta o guard de dado velho (`stale`).
    days_since_last_run: int | None = None

    @property
    def has_data(self) -> bool:

        return self.direction != EVO_INSUFFICIENT

    @property
    def stale(self) -> bool:
        """A leitura reflete um momento passado: faz tempo demais desde a
        última corrida, então NÃO vale dar o veredito como se fosse de agora
        (o corpo já pode ter mudado). O writer avisa; a diretriz de plano e a
        linha do recap se calam."""

        return (
            self.days_since_last_run is not None
            and self.days_since_last_run > EVO_STALE_AFTER_DAYS
        )

    @property
    def improving(self) -> bool:

        return self.direction == EVO_IMPROVING

    @property
    def mixed(self) -> bool:

        return self.confidence == EVO_MIXED
