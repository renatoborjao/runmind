from contextvars import ContextVar
from datetime import date, datetime
from zoneinfo import ZoneInfo

# Fuso PADRÃO do produto (e do scheduler). Toda data "de hoje" deve vir daqui:
# usar datetime.now(UTC).date() vira o dia às 21h no Brasil e joga cálculos
# semanais (plano, resumo, consistência) para a semana ISO errada.
DEFAULT_TIMEZONE = ZoneInfo("America/Sao_Paulo")

# Fuso do ATLETA em processamento. `now_local`/`today_local` leem daqui, então
# basta setar UMA vez no ponto de entrada (chat, análise, cada notifier) e todo
# cálculo de data a jusante fica no fuso certo — sem tocar nos 89 call sites.
# Default = Brasil (mantém o comportamento de quem não tem fuso próprio).
_active_tz: ContextVar[ZoneInfo] = ContextVar(
    "active_tz",
    default=DEFAULT_TIMEZONE,
)


def _to_zone(tz) -> ZoneInfo:
    """Aceita ZoneInfo, string ("Europe/Lisbon") ou None -> ZoneInfo válido;
    fuso inválido/ausente cai no padrão (nunca levanta)."""

    if isinstance(tz, ZoneInfo):

        return tz

    if not tz:

        return DEFAULT_TIMEZONE

    try:

        return ZoneInfo(str(tz))

    except Exception:

        return DEFAULT_TIMEZONE


def use_athlete_timezone(tz) -> None:
    """Fixa o fuso do atleta em processamento. Chamar nos pontos de entrada,
    logo após carregar o perfil (runner.timezone)."""

    _active_tz.set(_to_zone(tz))


def active_timezone() -> ZoneInfo:

    return _active_tz.get()


def now_local() -> datetime:

    return datetime.now(_active_tz.get())


def today_local() -> date:

    return now_local().date()


def now_in(tz) -> datetime:
    """Agora num fuso ESPECÍFICO, sem depender do contexto ativo — pra o
    disparador decidir se é a hora local daquele atleta."""

    return datetime.now(_to_zone(tz))
