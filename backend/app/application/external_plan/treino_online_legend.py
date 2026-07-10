"""Legenda dos códigos do 'Treino Online' — a ferramenta do treinador do
Mauricio. Os planos vêm com siglas (CCR, IT, TR...) que, sem tradução,
chegariam cruas na análise. Ensinar a legenda ao parser (e ter o mapa pro
nosso vocabulário) faz o coach entender o que foi PRESCRITO e comparar com o
executado.

Fácil de estender: outros treinadores/ferramentas ganham a própria legenda."""

# código do Treino Online -> (nome legível, tipo interno do RunMind)
# tipo interno None = não é corrida/caminhada (ignorado no plano).
TREINO_ONLINE = {
    "AL": ("Alongamentos", None),
    "BIKE": ("Pedalar", None),
    "CAM": ("Caminhada", "WALK"),
    "CCL": ("Corrida Contínua Lenta", "EASY"),
    "CCR": ("Corrida Contínua Rápida", "TEMPO"),
    "CROSS T": ("Corrida em Trilhas", "EASY"),
    "CT": ("Circuito (Circuit Training)", None),
    "DAY OFF": ("Descanso", None),
    "FF": ("Forte e Fraco (variação de ritmo)", "FARTLEK"),
    "IT": ("Intervalado (tiros)", "VO2"),
    "MUSC": ("Musculação", None),
    "NAT": ("Natação", None),
    "PROVA": ("Prova ou Evento", "RACE"),
    "RAMPAS/ACLIVES": ("Tiros em Aclives (rampas)", "VO2"),
    "TT": ("Treino Técnico", "EASY"),
    "TR": ("Trote (trotar)", "RECOVERY"),
}


def legend_for_prompt() -> str:
    """Texto da legenda pra injetar no prompt de extração — o Gemini expande
    a sigla em vez de devolver o código cru."""

    lines = [
        f"  {code} = {label}"
        for code, (label, _) in TREINO_ONLINE.items()
    ]

    return "\n".join(lines)


def internal_type(code: str) -> str | None:
    """Tipo interno do RunMind pra uma sigla (None se não for corrida)."""

    entry = TREINO_ONLINE.get((code or "").strip().upper())

    return entry[1] if entry else None
