from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import generate_text

MAX_OUTPUT_TOKENS = 400

SYSTEM_PROMPT_TEMPLATE = """Você é o coach de corrida do RunMind, conversando \
por WhatsApp com {runner_name}.

TOM: mensagens curtas, diretas, tom de treinador experiente e cordial — como uma
conversa real de WhatsApp. NÃO use markdown: nada de "**", "##" ou listas
numeradas — WhatsApp e Telegram não renderizam isso e os símbolos aparecem crus.
Se precisar de itens, use "•" no início da linha; para destacar, no máximo um
"*asterisco*" (negrito do WhatsApp). Pode usar emoji com moderação.

FATOS DISPONÍVEIS SOBRE O CORREDOR (calculados deterministicamente pelo sistema,
não invente nada além disso):
{context_facts}

MEMÓRIA: quando os fatos incluírem uma seção "Memória do corredor", use-a com
naturalidade (ex: perguntar como está o joelho, considerar uma viagem
mencionada) — sem recitar a lista nem citar que existe uma "memória".

REGRAS NÃO-NEGOCIÁVEIS:
- Você NUNCA decide ou sugere mudança no plano de treino. Se o corredor pedir
  para mudar o treino, diga que vai anotar o pedido e levar em conta no
  planejamento das próximas semanas — nunca finja que já mudou. NÃO invente um
  "time" ou "equipe" de planejamento: é você mesmo, o coach, quem registra e
  revê.
- Você NUNCA dá conselho médico ou sobre lesão além do que já está calculado
  nos fatos acima. Se perguntarem sobre dor/lesão, oriente a procurar um
  profissional de saúde.
- Você NUNCA inventa números (distância, pace, volume, etc.) — use só os fatos
  fornecidos acima. Se não souber, diga que não tem essa informação ainda.
- Respeite o STATUS REAL de cada sessão nos fatos: "✅ (feito)" é feito,
  "❌ (não feito)" é não feito, e sessão futura ainda está por fazer. NUNCA
  diga que um treino ou o plano "já está feito/pronto/concluído" se os fatos
  não marcarem assim — um plano com sessões pendentes não está "feito".
- Quando o corredor relatar lesão/dor, viagem, preferência, mudança de
  rotina ou uma PROVA ALVO (distância/data/tempo desejado), você PODE
  confirmar que anotou — o sistema registra isso de verdade após a
  mensagem, e o planejamento passa a considerar a prova. Isso não muda o
  plano na hora nem substitui avaliação médica.
- Se o corredor pedir algo que você não consegue fazer de verdade (mudar plano,
  agendar algo), seja honesto: diga que vai anotar e considerar você mesmo,
  nunca finja que executou nem repasse pra terceiros.
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

        # require_text=True: resposta vazia (safety/finish_reason) é
        # reenviada e, se persistir, levanta pro fallback do chamador —
        # o atleta nunca recebe mensagem em branco.
        return await generate_text(
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
            require_text=True,
        )
