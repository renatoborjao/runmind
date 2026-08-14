from dataclasses import dataclass


@dataclass(slots=True)
class DailyCheckin:
    """Estado SUBJETIVO relatado pelo atleta — como ele SE SENTE, o eixo que o
    relógio não mede. Complementa a leitura do corpo (objetiva, do Garmin): o
    sRPE e a sensação valem tanto quanto HRV/sono. Campos 1-5, todos opcionais
    (o atleta raramente relata tudo de uma vez).

    Escalas (1-5): energia 1=exausto/5=cheio; sono 1=péssimo/5=ótimo;
    dor 1=nenhuma/5=muita (dor é a única em que MAIOR = pior).
    Ver [[project_ideias_produto]] item 4."""

    day: str                       # data local ISO (YYYY-MM-DD)
    at: str                        # datetime ISO da captura
    energy: int | None = None
    sleep_quality: int | None = None
    soreness: int | None = None
    illness: bool = False          # relatou estar doente (gripe/febre/resfriado)
    note: str = ""                 # ex.: "dor na panturrilha direita"

    @property
    def has_data(self) -> bool:

        return (
            any(
                v is not None
                for v in (self.energy, self.sleep_quality, self.soreness)
            )
            or self.illness
            or bool(self.note)
        )
