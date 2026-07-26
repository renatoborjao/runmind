from dataclasses import dataclass


@dataclass(slots=True)
class ReadinessDiaryEntry:
    """Uma avaliação de prontidão registrada — o 'diário do que o coach diria'.
    Em modo observação nada é enviado; grava-se aqui pra o Renato conferir o
    veredito e o dedup por mudança de estado antes de ligar o envio real."""

    day: str                 # data local ISO (YYYY-MM-DD)
    at: str                  # datetime local ISO
    tier: str                # READINESS_* do veredito
    body_state: str          # estado do corpo que originou
    reason: str              # semente factual do veredito
    demand: str              # exigência do treino de hoje (DEMAND_*)
    would_notify: bool       # falaria HOJE? (should_speak + mudou de estado)
    from_tier: str | None = None   # estado anterior (dá pra ver a virada)
