from dataclasses import dataclass, field

# níveis de risco de lesão (sinal de coach, NÃO diagnóstico médico)
RISK_LOW = "LOW"
RISK_ELEVATED = "ELEVATED"
RISK_HIGH = "HIGH"


@dataclass(slots=True)
class InjuryRisk:
    """Risco de lesão ANTES de virar lesão: cruza o spike de carga (ACWR),
    a rampa de volume, a recuperação caindo e o histórico de lesão. É mais
    PRECOCE e amplo que o corpo STRAINED (que exige carga alta E recuperação
    caindo juntas) — pega o pico de carga antes da recuperação despencar.
    Sinal de coach, não diagnóstico. Ver [[project_ideias_produto]] item 27."""

    level: str = RISK_LOW
    reasons: list[str] = field(default_factory=list)  # o que puxou o risco

    @property
    def elevated(self) -> bool:

        return self.level in (RISK_ELEVATED, RISK_HIGH)
