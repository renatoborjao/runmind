import json

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.domain.entities.memory_entry import (
    MEMORY_CATEGORIES,
    MemoryEntry,
)

DEFAULT_MODEL = "gemini-2.5-flash"

MAX_OUTPUT_TOKENS = 400

EMPTY_OPS: dict = {"add": [], "archive": []}

EXTRACTION_PROMPT_TEMPLATE = """Você mantém a memória de longo prazo do coach \
de corrida do RunMind sobre o corredor {runner_name}.

Analise a MENSAGEM NOVA do corredor e decida se ela contém fatos duráveis que
o coach deve lembrar em conversas futuras. Categorias possíveis:
- lesao: dor, lesão ou desconforto físico relatado
- preferencia: preferências de treino (horário, terreno, tipo de treino...)
- disponibilidade: viagens, ausências, mudanças de agenda
- objetivo: mudança de meta ou prova alvo
- vida: evento de vida relevante ao treino (trabalho puxado, doença, sono...)
- outro: fato durável que não se encaixa acima

MEMÓRIAS ATIVAS ATUAIS (id — [categoria] conteúdo):
{current_memories}

ÚLTIMAS MENSAGENS DA CONVERSA (contexto):
{recent_turns}

MENSAGEM NOVA DO CORREDOR:
{incoming_text}

Responda APENAS com JSON neste formato:
{{"add": [{{"category": "...", "content": "..."}}], "archive": ["id"]}}

REGRAS:
- Só fatos duráveis. Perguntas, cumprimentos e comentários sobre um treino
  pontual NÃO geram memória.
- "content" em uma linha curta, em português, terceira pessoa implícita
  (ex: "Dor no joelho direito").
- NÃO duplique memória ativa existente (nem com outras palavras).
- Se a mensagem indicar que um fato registrado se resolveu ou mudou
  (ex: "o joelho melhorou"), inclua o id correspondente em "archive".
- Sem fatos novos e nada a arquivar: {{"add": [], "archive": []}}
"""


class MemoryExtractionEngine:

    @staticmethod
    async def extract(
        runner_name: str,
        current_memories: list[MemoryEntry],
        recent_turns: list[dict],
        incoming_text: str,
    ) -> dict:

        settings = get_settings()

        client = genai.Client(
            api_key=settings.google_api_key,
        )

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            runner_name=runner_name,
            current_memories=MemoryExtractionEngine._render_memories(
                current_memories,
            ),
            recent_turns=MemoryExtractionEngine._render_turns(
                recent_turns,
            ),
            incoming_text=incoming_text,
        )

        response = await client.aio.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                # extração estruturada não precisa de raciocínio; com
                # thinking ligado os tokens de pensamento estouram o
                # max_output_tokens e o JSON volta vazio (flaky)
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
        )

        return MemoryExtractionEngine._parse_ops(
            response.text or "",
        )

    @staticmethod
    def _render_memories(
        memories: list[MemoryEntry],
    ) -> str:

        if not memories:

            return "(nenhuma)"

        return "\n".join(
            f"{entry.id} — [{entry.category}] {entry.content}"
            for entry in memories
        )

    @staticmethod
    def _render_turns(
        turns: list[dict],
    ) -> str:

        if not turns:

            return "(nenhuma)"

        return "\n".join(
            f"{turn['role']}: {turn['text']}"
            for turn in turns
        )

    @staticmethod
    def _parse_ops(
        raw: str,
    ) -> dict:

        try:

            data = json.loads(raw)

        except (json.JSONDecodeError, TypeError):

            return dict(EMPTY_OPS)

        if not isinstance(data, dict):

            return dict(EMPTY_OPS)

        add = [
            item
            for item in data.get("add", [])
            if isinstance(item, dict)
            and item.get("content")
            and item.get("category") in MEMORY_CATEGORIES
        ]

        archive = [
            entry_id
            for entry_id in data.get("archive", [])
            if isinstance(entry_id, str)
        ]

        return {
            "add": add,
            "archive": archive,
        }
