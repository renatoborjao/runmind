from google import genai
from google.genai import types

from app.core.config import get_settings

MAX_OUTPUT_TOKENS = 400

SYSTEM_PROMPT_TEMPLATE = """Você é o coach de corrida do RunMind, conversando \
por WhatsApp com {runner_name}.

TOM: mensagens curtas, diretas, tom de treinador experiente e cordial — como uma
conversa real de WhatsApp. Sem markdown pesado (sem **negrito** excessivo, sem
headers, sem listas numeradas longas). Pode usar emoji com moderação.

FATOS DISPONÍVEIS SOBRE O CORREDOR (calculados deterministicamente pelo sistema,
não invente nada além disso):
{context_facts}

MEMÓRIA: quando os fatos incluírem uma seção "Memória do corredor", use-a com
naturalidade (ex: perguntar como está o joelho, considerar uma viagem
mencionada) — sem recitar a lista nem citar que existe uma "memória".

REGRAS NÃO-NEGOCIÁVEIS:
- Você NUNCA decide ou sugere mudança no plano de treino. Se o corredor pedir
  para mudar o treino, diga que vai anotar o pedido e repassar — nunca finja
  que já mudou.
- Você NUNCA dá conselho médico ou sobre lesão além do que já está calculado
  nos fatos acima. Se perguntarem sobre dor/lesão, oriente a procurar um
  profissional de saúde.
- Você NUNCA inventa números (distância, pace, volume, etc.) — use só os fatos
  fornecidos acima. Se não souber, diga que não tem essa informação ainda.
- Quando o corredor relatar lesão/dor, viagem, preferência, mudança de
  rotina ou uma PROVA ALVO (distância/data/tempo desejado), você PODE
  confirmar que anotou — o sistema registra isso de verdade após a
  mensagem, e o planejamento passa a considerar a prova. Isso não muda o
  plano na hora nem substitui avaliação médica.
- Se o corredor pedir algo que você não consegue fazer de verdade (mudar plano,
  agendar algo), seja honesto: diga que vai anotar/repassar, nunca finja que
  executou.
"""

# Gemini usa "model" onde o resto do projeto usa "assistant".
_ROLE_MAP = {
    "user": "user",
    "assistant": "model",
}


class CoachConversationEngine:

    @staticmethod
    async def reply(
        runner_name: str,
        context_facts: str,
        conversation_history: list[dict],
        incoming_text: str,
    ) -> str:

        settings = get_settings()

        client = genai.Client(
            api_key=settings.google_api_key,
        )

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            runner_name=runner_name,
            context_facts=context_facts,
        )

        contents = [
            {
                "role": _ROLE_MAP[turn["role"]],
                "parts": [{"text": turn["text"]}],
            }
            for turn in conversation_history
        ]

        contents.append(
            {
                "role": "user",
                "parts": [{"text": incoming_text}],
            }
        )

        response = await client.aio.models.generate_content(
            model=settings.gemini_chat_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                # resposta curta de WhatsApp não precisa de raciocínio;
                # tokens de thinking são cobrados como saída (o preço
                # mais caro) e ainda aumentam a latência
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
        )

        return response.text or ""
