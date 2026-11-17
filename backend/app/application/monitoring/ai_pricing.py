"""Preço do Gemini num lugar só — usado pelo monitor do plano, pela auditoria diária e pelo
report_tokens. É uma ESTIMATIVA a partir dos tokens que o medidor grava: a fonte de verdade do
total é o painel do AI Studio (e o medidor não vê voz/TTS nem a pesquisa na web).

Preços OFICIAIS de lista, USD por 1M de tokens (entrada, saída — o raciocínio/thinking é cobrado
como saída), conferidos em aistudio.google.com/docs/pricing em 17/11/2026, faixa de prompt ≤200k.
O modo em LOTE (batch) custa a metade. O Flash 3.6 DOBRA de preço em 01/01/2027.
Antes daqui os scripts usavam preços de referência ~5× abaixo no Flash (subestimava a conta)."""

from datetime import date

USD_BRL = 5.40

PRICING = {
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.30, 2.50),
    "_default": (0.75, 3.75),
}

# mudança de preço anunciada: (a partir de, modelo) → (entrada, saída)
PRICE_CHANGES = {
    (date(2027, 1, 1), "gemini-3.6-flash"): (1.50, 7.50),
}

BATCH_DISCOUNT = 0.5


def price(model: str | None, when: date | None = None) -> tuple[float, float]:

    base = PRICING.get(model or "", PRICING["_default"])

    if when is None:

        return base

    for (start, name), changed in sorted(PRICE_CHANGES.items()):

        if name == model and when >= start:

            base = changed

    return base


def cost_brl(
    model: str | None,
    tokens_in: int,
    tokens_out: int,
    when: date | None = None,
    batch: bool = False,
) -> float:
    """Custo estimado em reais de UMA chamada. `tokens_out` já inclui o raciocínio."""

    pin, pout = price(model, when)

    usd = ((tokens_in or 0) * pin + (tokens_out or 0) * pout) / 1_000_000

    if batch:

        usd *= BATCH_DISCOUNT

    return usd * USD_BRL


def record_cost_brl(record: dict) -> float:
    """Custo de um registro do medidor (storage/token_usage/*.jsonl)."""

    when = None

    stamp = record.get("ts")

    if isinstance(stamp, str) and len(stamp) >= 10:

        try:

            when = date.fromisoformat(stamp[:10])

        except ValueError:

            when = None

    return cost_brl(
        record.get("model"),
        record.get("in") or 0,
        (record.get("out") or 0) + (record.get("thoughts") or 0),
        when,
    )
