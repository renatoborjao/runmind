import json
from dataclasses import dataclass

from google.genai import types

from app.core.clock import today_local
from app.core.config import get_settings
from app.domain.entities.memory_entry import MemoryEntry
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# classificação + confirmação curtas; extração estruturada não precisa de
# raciocínio (thinking ligado estoura o max_output e o JSON volta vazio)
MAX_OUTPUT_TOKENS = 500

# categorias válidas pra uma preferência de rotina (subconjunto de
# MEMORY_CATEGORIES): forma do treino/semana OU padrão de agenda
_CATEGORIES = {"preferencia", "disponibilidade"}

PROMPT_TEMPLATE = """Você é o treinador de corrida do Ritmind, cuidando de \
{runner_name}. Hoje é {today} (use pra resolver "a partir da semana que vem", \
"a partir de agosto" etc.).

O atleta mandou uma mensagem que PODE ser uma PREFERÊNCIA DURÁVEL sobre como a \
rotina/semana de treino deve ser montada DAQUI PRA FRENTE — não uma mudança só \
desta semana, não uma pergunta.

DIAS DE TREINO DEFINIDOS NO ONBOARDING (FIXOS): {training_days}
OBJETIVO DO ATLETA: {objective}

A preferência é COMPLEMENTAR a esses dois pilares — ela ajusta DURAÇÃO, RITMO, \
ESFORÇO ou COMO a semana é montada DENTRO dos dias fixos e a serviço da meta. \
Ela NUNCA redefine os dias de treino do onboarding nem abandona o objetivo:
- Se a mensagem citar dias ("só terça e quinta"), entenda como REFERÊNCIA aos \
dias que JÁ são dele (um subconjunto — ex.: os dias de semana dele), NÃO um \
pedido de trocar/remover dias. Trocar de dia é outro assunto (o atleta pediria \
explicitamente "quero passar a treinar em tal dia"). Na dúvida, preserve os \
dias do onboarding.
- Se a preferência conflitar com a meta (ex.: um teto de tempo que inviabiliza \
o longão que a prova exige), registre o pedido MAS deixe claro que o essencial \
rumo à meta é preservado (o coach faz o meio-termo ao montar o plano).
- O "content" deve deixar explícito que MANTÉM os dias do onboarding e a meta.

São preferências DURÁVEIS (durable=true), por exemplo:
- orçamento de tempo por treino/dia ("treinos de semana em até 50 min")
- ritmo/limite por período ("fim de semana sem pressa/sem limite de tempo")
- padrão de agenda que se repete ("dia de semana é sempre corrido")

NÃO é durável (durable=false):
- pedido pra mexer SÓ na semana de agora ("deixa a semana leve", "hoje pega leve")
- pergunta, elogio, comentário sobre UM treino pontual
- desabafo sem definir uma regra pra frente
- pedido de TROCAR os dias de treino (não é este fluxo)

MEMÓRIAS JÁ ANOTADAS (não duplique; se a nova SUBSTITUI uma, cite o id em
"archive"):
{current_memories}

ÚLTIMAS MENSAGENS (contexto):
{recent_turns}

MENSAGEM NOVA DO ATLETA:
"{message}"

Responda APENAS JSON.

Se NÃO for preferência durável:
{{"durable": false}}

Se FOR:
{{"durable": true,
  "category": "preferencia" ou "disponibilidade",
  "content": "fato durável em 1 linha, 3ª pessoa, com os detalhes e o horizonte \
(ex: 'Prefere treinos de dia de semana em até ~50 min (ter/qui, agenda \
corrida); fim de semana sem limite de tempo; a partir de 04/08')",
  "archive": ["id de memória que isto substitui, se houver"],
  "reply": "{reply_guidance}"}}
"""

_REPLY_OWNED = (
    "confirmação curta e calorosa de WhatsApp: mostra que ENTENDEU (repete os "
    "detalhes com as palavras dele) e diz que vai montar os PRÓXIMOS planos "
    "assim (não mexe na semana atual). Sem markdown, no máximo um emoji."
)

_REPLY_EXTERNAL = (
    "confirmação curta e calorosa de WhatsApp: mostra que ENTENDEU e anotou a "
    "preferência (o plano dele é do treinador humano, então NÃO prometa montar "
    "plano). Sem markdown, no máximo um emoji."
)


@dataclass(slots=True)
class TrainingPreference:

    category: str

    content: str

    reply: str

    # ids de memória que esta preferência substitui (ex.: trocou o orçamento
    # de tempo anterior) — arquivados junto pra não acumular contradição
    archive: list[str]


class TrainingPreferenceEngine:
    """IA-treinadora: decide se a mensagem é uma PREFERÊNCIA DURÁVEL de rotina
    (forma da semana daqui pra frente) e, se for, destila o fato pra memória +
    a confirmação pro atleta. Devolve None quando não é durável (aí o turno
    segue pros outros fluxos)."""

    @staticmethod
    async def extract(
        runner_name: str,
        current_memories: list[MemoryEntry],
        recent_turns: list[dict],
        incoming_text: str,
        plan_owned: bool,
        training_days: str,
        objective: str,
    ) -> TrainingPreference | None:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner_name,
            today=today_local().strftime("%d/%m/%Y"),
            training_days=training_days or "(não definidos)",
            objective=objective or "(não definido)",
            current_memories=TrainingPreferenceEngine._render_memories(
                current_memories,
            ),
            recent_turns=TrainingPreferenceEngine._render_turns(
                recent_turns,
            ),
            message=incoming_text.replace('"', "'"),
            reply_guidance=_REPLY_OWNED if plan_owned else _REPLY_EXTERNAL,
        )

        return await generate_json(
            model=settings.gemini_extract_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
            parse=TrainingPreferenceEngine._parse,
        )

    @staticmethod
    def _parse(raw: str) -> TrainingPreference | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict) or not data.get("durable"):

            return None

        category = data.get("category")

        content = str(data.get("content", "")).strip()

        reply = str(data.get("reply", "")).strip()

        if category not in _CATEGORIES or not content or not reply:

            return None

        archive = [
            entry_id
            for entry_id in data.get("archive", [])
            if isinstance(entry_id, str)
        ]

        return TrainingPreference(
            category=category,
            content=content,
            reply=reply,
            archive=archive,
        )

    @staticmethod
    def _render_memories(memories: list[MemoryEntry]) -> str:

        if not memories:

            return "(nenhuma)"

        return "\n".join(
            f"{entry.id} — [{entry.category}] {entry.content}"
            for entry in memories
        )

    @staticmethod
    def _render_turns(turns: list[dict]) -> str:

        if not turns:

            return "(nenhuma)"

        return "\n".join(
            f"{turn['role']}: {turn['text']}"
            for turn in turns
        )
