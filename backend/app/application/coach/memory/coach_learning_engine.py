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
corrida do Ritmind. Sua função aqui NÃO é conversar nem montar treino — é
APRENDER sobre o corredor {runner_name} observando o que ele FEZ (não o que
disse), pra que o coach lembre disso ao montar os próximos planos e ao cuidar
dele no dia a dia.

É VIDA REAL e MUDA: a rotina muda, aparecem compromissos, tem semana que ele
cumpre à risca, tem semana que faz treino extra, tem semana que fura. Seu
retrato tem que ser VIVO — reconfirma o que se manteve, deixa MORRER o que a
vida mudou, e só vira padrão o que se REPETE. Nada aqui é rótulo permanente.

APRENDIZADOS ATIVOS ATUAIS (id — [categoria] conteúdo):
{current_learnings}

EVIDÊNCIA DESTA SEMANA (o que o coach prescreveu × o que de fato aconteceu):
{week_evidence}

Categorias de aprendizado:
- aderencia: o que ele CUMPRE ou FURA de forma consistente (um dia/tipo/formato)
- preferencia_revelada: preferência que o COMPORTAMENTO revela (não algo que
  ele declarou — isso é outra memória)
- limite: teto de capacidade observado — tanto o que ele AINDA NÃO sustenta
  quanto o que ele JÁ SUSTENTA com folga (capacidade demonstrada informa que
  dá pra ser mais ambicioso)
- resposta: como o corpo dele responde ao estímulo — INCLUSIVE resposta BOA
  (recupera bem, tolera tal carga/ACWR), a resposta ao TREINO ao longo do tempo
  (evolui/estagna na forma aeróbica, responde ao estímulo de qualidade), como
  ele PERCEBE o esforço (RPE alto/baixo pro que a FC media diz) e traço
  ESTRUTURAL que persiste mesmo em semana verde (ex.: sono cronicamente curto
  mesmo com o corpo equilibrado)

Responda APENAS com JSON:
{{"add": [{{"category": "...", "content": "..."}}],
  "reconfirm": ["id"],
  "archive": ["id"]}}

REGRAS (o retrato é VIVO, não engessado):
- Aprenda tanto o POSITIVO quanto o negativo. Uma semana BOA também ensina
  (teto que ele sustenta, resposta boa, traço estrutural). MAS não registre
  "cumpriu o plano" nem nada que os NÚMEROS da semana já mostram sozinhos
  (aderência e estado do corpo já vão ao coach ao vivo) — só o que agrega ALÉM
  do óbvio.
- PADRÃO DE ADERÊNCIA (fura tal dia/treino) só é padrão com REPETIÇÃO em 2-3
  semanas DIFERENTES. Um furo isolado, dois furos esparsos, ou furo com CAUSA
  PONTUAL conhecida (viagem, lesão, prova, compromisso que ele contou) NÃO é
  padrão. Use as contagens "N de M vezes": se N é pequeno perto de M, NÃO é
  padrão.
- TREINO EXTRA não-prescrito NÃO é furo — é sinal de disposição/preferência.
- MOVER um treino de dia e cumprir = cumprido, NÃO furado.
- Prefira frasear de forma ESTRUTURAL (dura) e não episódica: "sono é
  limitador recorrente" dura; "HRV caiu esta semana" envelhece em dias.
- DEVAGAR PRA CRIAR, DEVAGAR PRA SOLTAR (histerese): assim como um padrão
  precisa de 2-3 semanas pra nascer, NÃO o derrube por UMA semana contrária —
  um aprendizado durável que teve só uma semana fora ainda vale; deixe a
  validade natural desgastar o que parou de se confirmar. Só use "archive"
  quando a evidência CONTRADIZ de forma clara e sustentada (ele mudou de vez).
- Se a evidência CONFIRMA um aprendizado ativo, coloque o id em "reconfirm"
  (NUNCA duplique em "add", nem crie um quase-igual sob outra categoria).
- "content" em UMA linha curta, português, terceira pessoa implícita
  (ex.: "Sustenta rampa de volume com ACWR ~1.1 sem quebrar").
- Prefira POUCOS aprendizados de alto sinal a muitos. Nada de novo, nada a
  confirmar, nada a arquivar: {{"add": [], "reconfirm": [], "archive": []}}
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
