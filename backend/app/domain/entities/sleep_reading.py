from dataclasses import dataclass

from app.domain.entities.body_reading import STABLE

# quanto o corpo pede por noite pra treinar bem (piso saudável). Abaixo disso,
# na média, é DÍVIDA de sono — o limitador nº1 da evolução pra quem dorme pouco.
HEALTHY_FLOOR_HOURS = 7.0


@dataclass(slots=True)
class SleepReading:
    """O sono como EIXO PRÓPRIO (não só uma etiqueta de 'limitador'): quanto,
    a tendência, a regularidade e a dívida. Todos os campos opcionais — sem
    relógio/sem noites medidas, fica vazio e a leitura se cala. Ver
    [[project_analise_corpo_garmin]] e [[project_ideias_produto]] (coaching de sono)."""

    avg_hours: float | None = None
    direction: str = STABLE            # tendência das horas (RISING = dormindo mais)
    nights_counted: int = 0
    short_nights: int = 0              # noites abaixo do piso saudável
    last_night_hours: float | None = None
    consistency: str = "unknown"       # "regular" | "irregular" | "unknown"
    sleep_score: int | None = None     # nota da própria Garmin (recente), se houver
    deep_avg_hours: float | None = None
    debt: bool = False                 # média abaixo do piso saudável

    @property
    def has_data(self) -> bool:
        """True quando houve pelo menos uma noite medida na janela."""

        return self.nights_counted > 0
