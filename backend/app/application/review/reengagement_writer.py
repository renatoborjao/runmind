"""Escreve o cutução de RE-ENGAJAMENTO — o coach indo atrás do atleta que
sumiu. Híbrido: a IA escreve (generate_text) ancorada em QUEM é o atleta (última
corrida, ritmo típico, o PORQUÊ dele de correr, objetivo); falha/vazio cai no
texto determinístico (nunca vira silêncio, [[feedback_conversa_viva]]).

Régua não-negociável: acolher, NUNCA cobrar/culpar. Um convite leve, curto, com
a porta aberta — orientamos, o atleta decide ([[feedback_orientar_nao_mandar]]).
Ancorado no histórico ([[feedback_base_historico_sempre]]), nunca genérico."""

from google.genai import types

from app.application.coach.context.athlete_brief import AthleteLongTermBrief
from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import generate_text

THINKING_BUDGET = 256

MAX_OUTPUT_TOKENS = 400

_SYSTEM_PROMPT = """Você é o coach de corrida do Ritmind. O atleta sumiu — sem \
treino e sem conversa há um tempo. Escreva UMA mensagem curta pra reaproximar \
(WhatsApp/Telegram, tom de treinador que se importa, sem markdown).

REGRAS NÃO-NEGOCIÁVEIS:
- ACOLHA, nunca cobre nem faça sentir culpa. Nada de "você falhou", "cadê \
você", "está abandonando". Nada de sermão.
- Comece reconhecendo com leveza que faz um tempo, de forma humana e curiosa \
("tá tudo bem?", "senti sua falta por aqui").
- Ancore em ALGO REAL dos fatos (a última corrida dele, o ritmo que ele \
costuma ter, o PORQUÊ dele de correr, o objetivo) — personalize, nunca genérico.
- UM convite leve e concreto pra retomar, do tamanho do momento (um trote \
gostoso, sem pressão de pace/volume). A decisão é dele.
- Deixe a porta aberta: você está por aqui quando ele quiser.
- Curto: 2-4 frases. Uma pergunta no fim convida a responder.

FATOS (do sistema; não invente além disso):
{facts}"""


class ReengagementWriter:

    @staticmethod
    async def write(profile: str, facts: str) -> str:

        prompt = _SYSTEM_PROMPT.format(facts=facts)

        try:

            text = await generate_text(
                model=get_settings().gemini_coach_model,
                contents=[
                    {"role": "user", "parts": [{"text": "(reaproximar o atleta)"}]}
                ],
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=THINKING_BUDGET,
                    ),
                ),
                require_text=True,
            )

            return text.strip()

        except Exception as e:  # noqa: BLE001 — nunca vira silêncio

            print(f"Re-engajamento (IA) falhou p/ '{profile}': {e}")

            return ReengagementWriter._fallback(facts)

    @staticmethod
    def facts(
        name: str,
        days_silent: int,
        last_run_desc: str | None,
        cadence_desc: str | None,
        goal_desc: str | None,
        motivation: str | None,
        profile: str,
    ) -> str:
        """Monta o bloco de fatos pro prompt — só o que existe entra."""

        lines = [f"Atleta: {name}", f"Dias sem treino nem conversa: {days_silent}"]

        if last_run_desc:

            lines.append(f"Última corrida: {last_run_desc}")

        if cadence_desc:

            lines.append(f"Ritmo habitual de treino: {cadence_desc}")

        if goal_desc:

            lines.append(f"Objetivo dele: {goal_desc}")

        if motivation:

            lines.append(f"O porquê dele de correr: {motivation}")

        brief = AthleteLongTermBrief.render(profile)

        if brief:

            lines.append(brief)

        return "\n".join(lines)

    @staticmethod
    def _fallback(facts: str) -> str:
        """Texto acolhedor mínimo — o atleta nunca percebe que a IA caiu. Sem
        números (os fatos podem não ter nome), só a mão estendida."""

        return (
            "Ei, senti sua falta por aqui! 🙂 Faz um tempinho que a gente não "
            "se fala nem bate um treino. Tá tudo bem?\n\n"
            "Quando quiser voltar, que tal um trote leve e gostoso, sem "
            "pressão de ritmo? Tô por aqui pra te ajudar a retomar no seu "
            "tempo. Bora?"
        )
