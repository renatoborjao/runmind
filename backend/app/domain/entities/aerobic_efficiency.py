from dataclasses import dataclass

# tendência da eficiência aeróbica (o eixo "estou evoluindo?")
EFF_IMPROVING = "IMPROVING"        # corre mais rápido pra cada batimento → mais em forma
EFF_STABLE = "STABLE"              # eficiência estável no período
EFF_DECLINING = "DECLINING"        # mais batimentos pro mesmo ritmo → algo pesando
EFF_INSUFFICIENT = "INSUFFICIENT"  # poucas corridas aeróbicas comparáveis pra concluir


@dataclass(slots=True)
class AerobicEfficiency:
    """Eficiência aeróbica ao longo do tempo — a resposta ao "estou evoluindo?".

    Fitness aeróbico = correr mais rápido para cada batimento. O sinal é o
    Efficiency Factor (velocidade ÷ FC média) das corridas EASY/aeróbicas
    comparáveis: se sobe ao longo das semanas, o corpo ficou mais econômico
    (mais em forma). É a evolução que a carga/recuperação não conta — carga diz
    'você está aguentando', isto diz 'você está melhorando'.

    Para virar número tangível, a tendência é traduzida de duas formas
    equivalentes: no MESMO pace, a FC caiu X bpm; ou na MESMA FC, o pace
    melhorou Y s/km. Puro/determinístico — o writer só narra."""

    direction: str = EFF_INSUFFICIENT

    runs_counted: int = 0
    weeks_covered: int = 0

    # Efficiency Factor (velocidade m/s ÷ FC) mediano de cada metade da janela
    ef_recent: float | None = None
    ef_earlier: float | None = None

    # âncoras representativas da janela (pra traduzir a variação em algo sentível)
    ref_hr: int | None = None       # FC de referência (mediana das corridas)
    ref_pace: float | None = None   # pace de referência min/km (mediana)

    # tradução da variação (sinal positivo = melhora)
    pace_gain_sec: int | None = None   # s/km mais rápido na MESMA FC
    hr_drop_bpm: int | None = None     # bpm a menos no MESMO pace

    # teto de credibilidade: uma rampa dramática (iniciante evoluindo rápido)
    # gera um número REAL porém incrível (ex.: 105 s/km) que soa como bug. Acima
    # de um limite plausível, guardamos o TETO e marcamos capped=True — o writer
    # fraseia "mais de X" (honesto e crível) em vez de cuspir o número cru.
    pace_gain_capped: bool = False
    hr_drop_capped: bool = False

    @property
    def has_data(self) -> bool:

        return self.direction != EFF_INSUFFICIENT

    @property
    def improving(self) -> bool:

        return self.direction == EFF_IMPROVING
