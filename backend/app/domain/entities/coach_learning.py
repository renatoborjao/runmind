from __future__ import annotations

from dataclasses import dataclass

# Categorias de aprendizado do coach — o que ele APRENDE observando o atleta
# (comportamento e resultado), diferente da memória evolutiva (fatos que o
# atleta DECLARA em conversa).
COACH_LEARNING_CATEGORIES = (
    "aderencia",            # o que ele cumpre de fato (dia/tipo/formato)
    "preferencia_revelada",  # preferência revelada por comportamento, não fala
    "limite",               # teto de capacidade observado
    "resposta",             # resposta fisiológica a um estímulo
)


@dataclass(slots=True)
class CoachLearning:
    """Uma lição durável que o coach aprendeu sobre ESTE atleta a partir do
    que ele fez (não do que disse). Nasce com validade (expires_at) — sem
    esquecimento, uma verdade antiga ("não corre 5 km") vira âncora que
    impede a evolução. Reconfirmar (nova evidência) empurra a validade
    adiante e sobe evidence_count."""

    id: str

    category: str

    content: str

    source: str

    # hora local (ISO) de quando foi aprendido
    created_at: str

    # hora local (ISO) até quando vale sem nova evidência — depois disso
    # o render/active ignora (esquecimento)
    expires_at: str

    # quantas semanas de evidência já sustentaram este aprendizado
    evidence_count: int = 1

    # TAGS para o cérebro coletivo futuro (passo 5): permitem agregar
    # aprendizados entre atletas do mesmo nível/objetivo sem refazer nada
    level: str | None = None

    goal_kind: str | None = None

    status: str = "active"
