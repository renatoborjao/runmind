"""Consumo de IA (Gemini) por atleta — tokens e custo-sombra em reais.

HOJE o RunMind roda no TIER GRÁTIS do Gemini: o custo real é R$ 0,00 (o limite
é rate-limit/429, não dinheiro). O valor em reais aqui é o CUSTO-SOMBRA: quanto
SERIA se fosse cobrado pelos preços de lista — pra dimensionar o negócio e
saber quanto cada atleta 'custaria' de IA num plano pago.

Os preços abaixo são de REFERÊNCIA (USD por 1M tokens) — ajuste PRICING com a
tabela oficial vigente. Cobrança do Gemini: thinking conta como saída.

O medidor (`TokenMeter`) começou em 2026-09-04, então o total reflete a janela
desde então, não a vida toda do atleta.

Uso:
  python report_tokens.py
"""

from app.application.monitoring.token_meter import TokenMeter
from app.infrastructure.persistence.token_usage_repository import (
    TokenUsageRepository,
)

# câmbio USD->BRL (ajuste conforme o dia)
USD_BRL = 5.40

# preços de REFERÊNCIA por modelo, USD por 1M tokens (input, output).
# thinking é cobrado como output. Ajuste com a tabela oficial do Gemini.
PRICING = {
    "gemini-3.6-flash": (0.15, 0.60),
    "gemini-3.5-flash-lite": (0.075, 0.30),
    "gemini-3.1-pro-preview": (1.25, 10.00),
    "_default": (0.15, 0.60),
}


def _cost_brl(model: str, in_t: int, out_billable: int) -> float:

    price_in, price_out = PRICING.get(model, PRICING["_default"])

    usd = (in_t * price_in + out_billable * price_out) / 1_000_000

    return usd * USD_BRL


def _report_cost(report: dict) -> float:
    """Custo-sombra do atleta somando por modelo (preço difere por modelo).
    Reconstrói in/out por modelo lendo os registros crus — o report agrega
    total por modelo, mas o custo precisa separar entrada de saída."""

    records = TokenUsageRepository().read(report["profile"])

    total = 0.0

    for r in records:

        in_t = r.get("in", 0)

        out_billable = r.get("out", 0) + r.get("thoughts", 0)

        total += _cost_brl(r.get("model", "_default"), in_t, out_billable)

    return total


def main() -> None:

    profiles = TokenUsageRepository().profiles()

    rows = [TokenMeter.report(p) for p in profiles]

    for row in rows:

        row["brl"] = _report_cost(row)

    rows.sort(key=lambda r: r["brl"], reverse=True)

    print()
    print("CONSUMO DE IA (GEMINI) POR ATLETA")
    print("Hoje = TIER GRÁTIS → custo real R$ 0,00. Abaixo = CUSTO-SOMBRA")
    print(f"(se fosse pago · câmbio US$1={USD_BRL} · medidor desde 2026-09-04)")
    print()

    header = (
        f"{'atleta':<14} {'chamadas':>8} {'tokens':>12} "
        f"{'R$ sombra':>10}  modelos"
    )
    print(header)
    print("-" * len(header))

    total_brl = 0.0

    for row in rows:

        total_brl += row["brl"]

        models = ", ".join(
            f"{m.split('-')[-1]}:{c['calls']}"
            for m, c in sorted(
                row["by_model"].items(),
                key=lambda kv: kv[1]["calls"],
                reverse=True,
            )
        )

        print(
            f"{row['profile'][:13]:<14} "
            f"{row['calls']:>8} "
            f"{row['total']:>12,} "
            f"R$ {row['brl']:>6.2f}  "
            f"{models}"
        )

    print("-" * len(header))
    print(f"{'TOTAL':<14} {'':>8} {'':>12} R$ {total_brl:>6.2f}")
    print()
    print("Por operação (onde a IA é gasta):")

    labels: dict[str, dict] = {}

    for row in rows:

        for label, cell in row["by_label"].items():

            agg = labels.setdefault(label, {"calls": 0, "total": 0})

            agg["calls"] += cell["calls"]

            agg["total"] += cell["total"]

    for label, cell in sorted(
        labels.items(), key=lambda kv: kv[1]["total"], reverse=True
    ):

        print(
            f"  {label:<12} {cell['calls']:>5} chamadas · "
            f"{cell['total']:>10,} tokens"
        )

    print()
    print("⚠ R$ é ESTIMATIVA (tier grátis = R$0 hoje). Ajuste PRICING/câmbio")
    print("  no topo do script com a tabela oficial do Gemini.")
    print()


if __name__ == "__main__":

    main()
