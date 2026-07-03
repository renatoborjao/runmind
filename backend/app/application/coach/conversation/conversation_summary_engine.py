from google import genai
from google.genai import types

from app.core.config import get_settings

MAX_OUTPUT_TOKENS = 400

SUMMARY_PROMPT_TEMPLATE = """Você mantém o resumo corrido das conversas \
entre o coach de corrida do RunMind e o corredor {runner_name}.

RESUMO ATUAL (conversas mais antigas):
{current_summary}

NOVOS TRECHOS DA CONVERSA (saindo da janela recente):
{turns}

Atualize o resumo incorporando os novos trechos. Regras:
- Um parágrafo corrido em pt-BR, no máximo ~120 palavras.
- Foque no fio da conversa: tópicos discutidos, dúvidas do corredor,
  orientações dadas, combinações ("vai tentar X", "semana que vem Y").
- NÃO repita métricas que o sistema já calcula (volume, pace, plano) nem
  fatos duráveis óbvios (lesões, viagens) — eles são registrados à parte.
- Descarte small talk sem valor. Se nada relevante, devolva o resumo
  atual como está.

Responda APENAS com o texto do resumo atualizado.
"""


class ConversationSummaryEngine:

    @staticmethod
    async def summarize(
        runner_name: str,
        current_summary: str,
        turns: list[dict],
    ) -> str:

        settings = get_settings()

        client = genai.Client(
            api_key=settings.google_api_key,
        )

        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            runner_name=runner_name,
            current_summary=current_summary or "(nenhum ainda)",
            turns=ConversationSummaryEngine._render_turns(turns),
        )

        response = await client.aio.models.generate_content(
            model=settings.gemini_extract_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
        )

        updated = (response.text or "").strip()

        # resposta vazia não pode apagar o resumo existente
        return updated or current_summary

    @staticmethod
    def _render_turns(
        turns: list[dict],
    ) -> str:

        return "\n".join(
            f"{turn['role']}: {turn['text']}"
            for turn in turns
        )
