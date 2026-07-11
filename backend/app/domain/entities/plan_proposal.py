from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PlanProposal:
    """Uma mudança de plano que o coach PROPÔS e aguarda o 'sim' do atleta —
    o acordo antes de mexer. O candidato é calculado na hora da proposta e
    guardado aqui, pra ser aplicado IGUALZINHO no aceite (a IA é não-
    determinística: regerar no 'sim' entregaria algo diferente do que o
    atleta viu).

    operations: lista de mudanças a aplicar no plano da semana. Cada item:
      {"action": "replace", "day": "Tuesday", "session": {<PlannedSession>}}
      {"action": "drop",    "day": "Tuesday"}
    Mover um treino de dia = drop no dia antigo + replace no novo.
    """

    kind: str

    # segunda-feira (ISO) da semana que a proposta cobre — se a semana virar
    # antes do aceite, a proposta está obsoleta e não se aplica
    week_start: str

    # texto que o atleta viu (o preview da mudança) — o que ele está aceitando
    preview: str

    # hora local (ISO) em que foi proposta — base pra caducar propostas velhas
    created_at: str

    operations: list[dict] = field(default_factory=list)
