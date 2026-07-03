from datetime import date, datetime
from zoneinfo import ZoneInfo

# Fuso oficial do produto (o mesmo do scheduler). Toda data "de hoje"
# deve vir daqui: usar datetime.now(UTC).date() vira o dia às 21h no
# Brasil e joga cálculos semanais (plano, resumo, consistência) para a
# semana ISO errada.
DEFAULT_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def now_local() -> datetime:

    return datetime.now(DEFAULT_TIMEZONE)


def today_local() -> date:

    return now_local().date()
