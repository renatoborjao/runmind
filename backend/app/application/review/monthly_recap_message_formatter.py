"""Formata o recap mensal — pensado pra ser ENCAMINHADO, não só lido pelo
próprio atleta: abre citando o nome (faz sentido fora de contexto pra quem
recebe encaminhado) e fecha com uma assinatura leve da marca."""

from __future__ import annotations


class MonthlyRecapMessageFormatter:

    @staticmethod
    def format(
        runner_name: str,
        recap: dict,
        narrative: list[str] | None = None,
    ) -> str:

        lines = [
            f"🏃 RunMind — Recap de {recap['month_label']}",
            "",
            f"{runner_name} fechou {recap['month_label']} com:",
            f"• {recap['total_km']:.1f} km em {recap['total_runs']} treino(s)",
            f"• Maior treino do mês: {recap['longest_km']:.1f} km",
            f"• Consistência: {recap['consistency']:.0f}%",
        ]

        records = recap.get("records") or []

        if records:

            lines.append("")

            lines.append("Recordes batidos neste mês:")

            lines.extend(f"• {line}" for line in records)

        lines.append("")

        lines.extend(
            narrative
            or MonthlyRecapMessageFormatter._fallback_narrative(recap)
        )

        lines.append("")

        lines.append("Feito com 🏃 RunMind 💪")

        return "\n".join(lines)

    @staticmethod
    def _fallback_narrative(recap: dict) -> list[str]:
        """Sem a IA: uma frase honesta com os números, nunca silêncio."""

        return [
            f"Mais um mês de treino na conta: {recap['total_runs']} "
            f"treino(s) e {recap['total_km']:.1f} km. Bora pro próximo! 👊"
        ]
