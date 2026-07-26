from dataclasses import dataclass

# Conduta que o corpo pede HOJE, lida à luz do que o treino de hoje exige.
# É a decisão em cima do body_state (BodyReading), não uma releitura do corpo.
READINESS_BRAKE = "BRAKE"       # sobrecarga real → freia/alivia/descansa
READINESS_CAUTION = "CAUTION"   # recuperação caindo → se hoje é puxado, vá leve
READINESS_GREEN = "GREEN"       # recuperado e com espaço → pode puxar
READINESS_NEUTRAL = "NEUTRAL"   # tudo ok / sem veredito → nada a dizer

READINESS_TIERS = frozenset(
    {READINESS_BRAKE, READINESS_CAUTION, READINESS_GREEN, READINESS_NEUTRAL}
)


@dataclass(slots=True, frozen=True)
class ReadinessVerdict:
    """O que o coach deve CONDUZIR hoje diante do corpo do atleta. Puro: sai do
    body_state (carga à luz da recuperação) cruzado com a exigência do treino de
    hoje. Quem decide ENVIAR (dedup por mudança de estado, horário, canal) é a
    camada de cima — aqui só dizemos o veredito e se ele, por si, merece voz."""

    tier: str
    reason: str                  # semente factual curta (o texto ao atleta vem depois)
    should_speak: bool           # merece fala proativa HOJE (antes do dedup de estado)
    body_state: str
    limiter: str | None = None
