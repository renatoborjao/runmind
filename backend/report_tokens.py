"""Consumo de IA (Gemini) por atleta — tokens e custo estimado em reais.

A conta do Gemini é PAGA (pré-paga). O valor aqui é uma ESTIMATIVA a partir dos tokens que o
medidor grava, no preço oficial de lista (app/application/monitoring/ai_pricing.py); a fonte de
verdade do total é o painel do AI Studio (o medidor não vê voz/TTS nem a pesquisa na web).

O medidor (`TokenMeter`) começou em 2026-09-04, então o total reflete a janela
desde então, não a vida toda do atleta.

Uso:
  python report_tokens.py
"""

from app.application.monitoring.token_meter import TokenMeter
from app.infrastructure.persistence.token_usage_repository import (
    TokenUsageRepository,
)

from app.application.monitoring.ai_pricing import USD_BRL, record_cost_brl  # noqa: E402


def _report_cost(report: dict) -> float:
    """Custo estimado do atleta somando por modelo (preço difere por modelo).
    Reconstrói in/out por modelo lendo os registros crus — o report agrega
    total por modelo, mas o custo precisa separar entrada de saída."""

    records = TokenUsageRepository().read(report["profile"])

    total = 0.0

    for r in records:

        total += record_cost_brl(r)

    return total


def main() -> None:

    profiles = TokenUsageRepository().profiles()

    rows = [TokenMeter.report(p) for p in profiles]

    for row in rows:

        row["brl"] = _report_cost(row)

    rows.sort(key=lambda r: r["brl"], reverse=True)

    print()
    print("CONSUMO DE IA (GEMINI) POR ATLETA")
    print("Conta PAGA. Abaixo = custo ESTIMADO (preço oficial; o painel do AI Studio é a verdade)")
    print(f"(estimado · câmbio US$1={USD_BRL} · medidor desde 2026-09-04)")
    print()

    header = (
        f"{'atleta':<14} {'chamadas':>8} {'tokens':>12} "
        f"{'R$ estim.':>10}  modelos"
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
    print("⚠ R$ é ESTIMATIVA. Preço e câmbio em app/application/monitoring/ai_pricing.py")
    print("  (conferir com o painel do AI Studio).")
    print()


if __name__ == "__main__":

    main()
