from dataclasses import dataclass


@dataclass(slots=True)
class SessionRpe:
    """Esforço percebido de UMA sessão (sRPE = duração × RPE).

    RPE (Rating of Perceived Exertion, escala 0-10 de Foster) é o quão puxado o
    atleta SENTIU o treino. sRPE = duração_min × RPE é a carga SUBJETIVA — o par
    de padrão-ouro do TRIMP (carga por FC): às vezes um treino de FC moderada
    'pesa' muito (fadiga acumulada, calor, cabeça), e só o RPE captura isso.
    Ver [[project_ideias_produto]] item 4 e [[project_analise_corpo_garmin]]."""

    activity_id: int
    day: str                 # data local ISO do treino
    duration_min: float
    rpe: int                 # 0-10
    srpe: float              # duração_min × rpe
    at: str                  # datetime ISO da captura
