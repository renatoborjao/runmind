from __future__ import annotations

from dataclasses import dataclass

# Categorias reconhecidas pela extração de memória.
MEMORY_CATEGORIES = (
    "lesao",
    "preferencia",
    "disponibilidade",
    "objetivo",
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
