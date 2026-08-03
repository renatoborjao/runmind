from __future__ import annotations

from dataclasses import dataclass

# Categorias reconhecidas pela extração de memória.
MEMORY_CATEGORIES = (
    "lesao",
    "preferencia",
    "disponibilidade",
    "objetivo",
    # o PORQUÊ profundo de correr / o que corrida significa pra ele / marcos de
    # identidade — a âncora emocional que faz o coach CONHECER o atleta
    "motivacao",
    "vida",
    "outro",
)


@dataclass(slots=True)
class MemoryEntry:

    id: str

    category: str

    content: str

    source: str

    created_at: str

    status: str = "active"
