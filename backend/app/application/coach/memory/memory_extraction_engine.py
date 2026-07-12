import json
from datetime import date

from google.genai import types

from app.core.clock import today_local
from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)
from app.domain.entities.memory_entry import (
    MEMORY_CATEGORIES,
    MemoryEntry,
)

MAX_OUTPUT_TOKENS = 400

EMPTY_OPS: dict = {"add": [], "archive": []}

EXTRACTION_PROMPT_TEMPLATE = """Você mantém a memória de longo prazo do coach \
de corrida do RunMind sobre o corredor {runner_name}.

Hoje é {today} (use para resolver datas relativas como "em agosto").

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

PROVA ALVO (opcional): se a mensagem definir ou mudar uma prova alvo do
corredor (distância e/ou data), inclua também:
"race": {{"name": "10 km", "date": "2026-08-15", "target_time": "00:50:00"}}
— campos desconhecidos: null; sem dia exato, use o dia 15 do mês citado.
Se disser que a prova foi cancelada ou já aconteceu:
"race": {{"clear": true}}

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

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            runner_name=runner_name,
            today=today_local().isoformat(),
            current_memories=MemoryExtractionEngine._render_memories(
                current_memories,
            ),
            recent_turns=MemoryExtractionEngine._render_turns(
                recent_turns,
            ),
            incoming_text=incoming_text,
        )

        ops = await generate_json(
            model=settings.gemini_extract_model,
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
            parse=MemoryExtractionEngine._parse_ops,
        )

        # JSON torto até o fim das tentativas -> não extrai nada neste turno
        # (o fato é recapturado quando o atleta mencionar de novo)
        return ops if ops is not None else dict(EMPTY_OPS)

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
    ) -> dict | None:
        """None em JSON torto/estrutura errada (pra o generate_json re-gerar);
        dict de ops (mesmo vazio) quando o JSON é válido."""

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
            and item.get("category") in MEMORY_CATEGORIES
        ]

        archive = [
            entry_id
            for entry_id in data.get("archive", [])
            if isinstance(entry_id, str)
        ]

        ops = {
            "add": add,
            "archive": archive,
        }

        race = MemoryExtractionEngine._parse_race(
            data.get("race"),
        )

        if race is not None:

            ops["race"] = race

        return ops

    @staticmethod
    def _parse_race(
        race,
    ) -> dict | None:

        if not isinstance(race, dict):

            return None

        if race.get("clear") is True:

            return {"clear": True}

        raw_date = race.get("date")

        if not isinstance(raw_date, str):

            return None

        try:

            date.fromisoformat(raw_date)

        except ValueError:

            return None

        return {
            "name": race.get("name"),
            "date": raw_date,
            "target_time": race.get("target_time"),
        }
