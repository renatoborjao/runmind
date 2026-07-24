import json

from google.genai import types

from app.core.config import get_settings
from app.domain.entities.coach_learning import (
    COACH_LEARNING_CATEGORIES,
    CoachLearning,
)
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

MAX_OUTPUT_TOKENS = 500

EMPTY_OPS: dict = {"add": [], "archive": [], "reconfirm": []}

EXTRACTION_PROMPT_TEMPLATE = """Você é o cérebro de longo prazo do coach de \
corrida do RunMind. Sua função aqui NÃO é conversar nem montar treino — é
APRENDER sobre o corredor {runner_name} observando o que ele FEZ nesta semana
(não o que ele disse), pra que o coach lembre disso ao montar os próximos
planos.

APRENDIZADOS ATIVOS ATUAIS (id — [categoria] conteúdo):
{current_learnings}

EVIDÊNCIA DESTA SEMANA (o que o coach prescreveu × o que de fato aconteceu):
{week_evidence}

Categorias de aprendizado:
- aderencia: o que ele CUMPRE de fato (um dia/tipo/formato que ele sempre
  faz — ou sempre fura)
- preferencia_revelada: preferência que o COMPORTAMENTO revela (não algo que
  ele declarou — isso é outra memória)
- limite: teto de capacidade observado (distância/volume/intensidade que ele
  ainda não sustenta)
- resposta: como o corpo dele responde a um estímulo (recuperação, ritmo,
  carga à luz do sono/HRV)

Responda APENAS com JSON:
{{"add": [{{"category": "...", "content": "..."}}],
  "reconfirm": ["id"],
  "archive": ["id"]}}

REGRAS:
- Só lição DURÁVEL e ACIONÁVEL sobre ESTE atleta. Um tropeço isolado NÃO é
  padrão — não vire aprendizado por uma semana atípica.
- PADRÃO DE ADERÊNCIA (fura tal dia/treino) exige REPETIÇÃO em semanas
  DIFERENTES. UM furo só, ou um furo com CAUSA PONTUAL conhecida (viagem,
  lesão, prova, imprevisto que ele contou no contexto de vida) NÃO é padrão —
  não gere aprendizado sobre isso.
- MOVER um treino de dia e cumprir NÃO é furar. Se ele fez a distância/tipo
  prescritos em outro dia, considere cumprido, não perdido.
- Se a evidência CONFIRMA um aprendizado ativo que já existe, coloque o id em
  "reconfirm" (NÃO duplique em "add").
- Se a evidência CONTRADIZ um aprendizado ativo (ele evoluiu, mudou), coloque
  o id em "archive".
- "content" em UMA linha curta, português, terceira pessoa implícita
  (ex.: "Sempre cumpre o tiro curto, mas fura o longão de domingo").
- Nada de novo, nada a confirmar, nada a arquivar:
  {{"add": [], "reconfirm": [], "archive": []}}
"""


class CoachLearningEngine:
    """Destila a evidência da semana em aprendizados duráveis sobre o atleta.
    Espelha o MemoryExtractionEngine (mesma blindagem de JSON, mesmo modelo de
    extração, thinking off), mas o insumo é COMPORTAMENTO/RESULTADO, não
    conversa."""

    @staticmethod
    async def extract(
        runner_name: str,
        current_learnings: list[CoachLearning],
        week_evidence: str,
    ) -> dict:

        settings = get_settings()

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            runner_name=runner_name,
            current_learnings=CoachLearningEngine._render_learnings(
                current_learnings,
            ),
            week_evidence=week_evidence or "(sem evidência esta semana)",
        )

        ops = await generate_json(
            model=settings.gemini_extract_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                # extração estruturada não precisa de raciocínio; com thinking
                # ligado os tokens de pensamento estouram o max_output e o
                # JSON volta vazio (mesmo bug da memória evolutiva)
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
            parse=CoachLearningEngine._parse_ops,
        )

        return ops if ops is not None else dict(EMPTY_OPS)

    @staticmethod
    def _render_learnings(
        learnings: list[CoachLearning],
    ) -> str:

        if not learnings:

            return "(nenhum ainda)"

        return "\n".join(
            f"{entry.id} — [{entry.category}] {entry.content}"
            for entry in learnings
        )

    @staticmethod
    def _parse_ops(
        raw: str,
    ) -> dict | None:
        """None em JSON torto (pra o generate_json re-gerar); dict de ops
        (mesmo vazio) quando o JSON é válido."""

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict):

            return None

        add = [
            item
            for item in data.get("add", [])
            if isinstance(item, dict)
            and item.get("content")
            and item.get("category") in COACH_LEARNING_CATEGORIES
        ]

        reconfirm = [
            entry_id
            for entry_id in data.get("reconfirm", [])
            if isinstance(entry_id, str)
        ]

        archive = [
            entry_id
            for entry_id in data.get("archive", [])
            if isinstance(entry_id, str)
        ]

        return {
            "add": add,
            "reconfirm": reconfirm,
            "archive": archive,
        }
