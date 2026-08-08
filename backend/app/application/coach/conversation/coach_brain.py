"""O CÉREBRO do coach na conversa — UM coach só, que conhece o atleta.

Toda interação é com o *coach*: ele tem o quadro completo (plano, calendário de
datas, corpo/evolução/sono, memória, últimos turnos) e, numa única chamada
estruturada, DECIDE o que fazer e responde na PRÓPRIA voz:

- responde uma pergunta (escolhendo o cartão EXATO quando o dado é denso —
  plano/paces/corpo — pra não desconfigurar número), OU
- propõe uma mudança no plano (com ESCOPO: uma sessão × a semana), OU
- interpreta a resposta a uma proposta pendente (aplicar/recusar/refinar), OU
- só conversa.

Substitui a cascata de detectores por palavra-chave (frágil, whack-a-mole —
ver [[project_roteador_acao_ia]], revertida). Atrás da flag COACH_BRAIN_ENABLED;
com a flag OFF roda a cascata determinística de sempre.

Blindagem ([[feedback_ia_json_blindada]]): saída estruturada + generate_json
(reparo/retry). Devolve None em falha — o chamador cai no caminho determinístico
(nunca silêncio, nunca regride). A EXECUÇÃO das ações é da camada determinística
(as "mãos"): o cérebro NUNCA finge que aplicou/mandou pro relógio."""

import json
from dataclasses import dataclass

from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# cartões EXATOS que o coach pode escolher pra responder (o dado sai
# determinístico, o coach só decide QUAL mostrar). Espelham os ChatIntent.
_CARDS = {
    "weekly_plan", "next_training", "last_training", "body", "fitness",
    "paces", "sleep", "race", "portrait", "help",
}

_ACTION_TYPES = {"move", "skip", "adjust", "simplify", "goal", "preference"}

_SCOPES = {"single_session", "week"}

_ON_PENDING = {"apply", "reject", "refine"}

MAX_OUTPUT_TOKENS = 700


PROMPT_TEMPLATE = """Você é o COACH de corrida do Ritmind, conversando por \
WhatsApp com {runner_name}. Você é UM coach só, que CONHECE o atleta — tem o \
histórico, os treinos, o corpo e as preferências dele no QUADRO abaixo. Toda \
resposta é SUA, na sua voz de treinador (direta, cordial, sem markdown).

QUADRO COMPLETO DO ATLETA (fatos determinísticos — use SÓ estes números, nunca \
invente nem arredonde):
{context_facts}
{pending_block}
Decida a MELHOR reação à mensagem do atleta e devolva UM JSON:

{{"say": "sua resposta ao atleta, na voz do coach",
  "answer_card": <um de: {cards} | null>,
  "action": null | {{"type": <move|skip|adjust|simplify|goal|preference>,
                     "scope": <single_session|week>,
                     "target_day": <dia em inglês|null>,
                     "instruction": "o que mudar, em 1 frase"}},
  "on_pending": null | <apply|reject|refine>}}

COMO ESCOLHER:
- Pergunta com DADO DENSO/EXATO (o plano da semana, o próximo treino, os paces/\
zonas, leitura de corpo, sono, evolução, estratégia de prova, o último treino, \
ajuda): preencha "answer_card" com o cartão certo — o sistema renderiza o dado \
EXATO. Ainda escreva um "say" curto na sua voz introduzindo (ex.: "Bora ver teu \
plano 👇"). "qual o treino de amanhã?" = next_training; "meu plano da semana" = \
weekly_plan; "meus paces/zonas" = paces; "como tá meu corpo" = body.
- Pedido de MUDAR o plano (mover de dia, pular, deixar mais leve/livre, \
simplificar pro relógio, trocar tipo, mudar objetivo, fixar dia do longão): \
preencha "action". ESCOPO é sagrado — se o atleta aponta UMA sessão ("o de \
amanhã", "só o longão"), scope="single_session" e target_day daquele dia; se \
fala da semana, scope="week". NUNCA mexa em mais do que ele pediu. Se ele muda o \
DIA de um treino (de X pra Y), o type é "move" (o target_day é o DESTINO) — \
mesmo que ele também peça pra deixar o treino diferente; o ajuste do conteúdo \
vem depois. Deixar mais leve/livre/sem pace SEM trocar de dia = "simplify" ou \
"adjust". NÃO aplique agora — o sistema monta a proposta e pergunta "posso \
aplicar?". No "say", reconheça o pedido.
- Se há PROPOSTA PENDENTE (bloco acima): a mensagem é a resposta a ela. \
"on_pending"="apply" se ele aceitou; "reject" se recusou; "refine" se está \
CORRIGINDO ("não é a semana, é o de amanhã", "sim mas 12km") — no refine, \
preencha TAMBÉM "action" com a versão corrigida (escopo certo).
- Senão, é conversa/relato/dúvida: responda no "say", com o que você sabe do \
atleta. Só isso.

REGRAS DURAS:
- Datas: use o CALENDÁRIO do quadro; "amanhã"/"hoje" já vêm resolvidos; nunca \
proponha dia que já passou.
- NUNCA diga que já aplicou/atualizou o plano ou que mandou pro relógio nesta \
mensagem — quem executa é o sistema depois do "sim". Não finja.
- Não dê conselho médico além do que está no quadro; dor/lesão → orientar \
procurar profissional.
- CONTEXTO DA CONVERSA: a mensagem pode dar sequência aos ÚLTIMOS TURNOS abaixo \
(ex.: "deixa livre" logo depois de falarem do treino de sábado = é o de sábado). \
Resolva referências pelo que já foi dito, não chute.
{history_block}
MENSAGEM DO ATLETA:
"{message}"
"""


@dataclass(slots=True)
class BrainAction:

    type: str

    scope: str

    target_day: str | None

    instruction: str


@dataclass(slots=True)
class BrainDecision:

    say: str

    answer_card: str | None = None

    action: BrainAction | None = None

    on_pending: str | None = None


class CoachBrain:

    @staticmethod
    async def decide(
        runner_name: str,
        context_facts: str,
        incoming_text: str,
        pending_preview: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> BrainDecision | None:
        """Uma decisão do coach (ou None em falha → cascata determinística)."""

        settings = get_settings()

        pending_block = ""

        if pending_preview:

            pending_block = (
                "\nPROPOSTA PENDENTE (o atleta está respondendo a esta):\n"
                f"{pending_preview}\n"
            )

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner_name,
            context_facts=context_facts,
            pending_block=pending_block,
            history_block=CoachBrain._history_block(conversation_history),
            cards="|".join(sorted(_CARDS)),
            message=incoming_text.replace('"', "'"),
        )

        return await generate_json(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=CoachBrain._parse,
        )

    # quantos turnos recentes o coach vê pra resolver referências ("deixa livre"
    # depois de falarem do treino de sábado). Poucos, pra não inflar o prompt.
    _HISTORY_TURNS = 6

    @staticmethod
    def _history_block(history: list[dict] | None) -> str:

        if not history:

            return ""

        recent = history[-CoachBrain._HISTORY_TURNS:]

        lines = [
            f"{'Atleta' if turn.get('role') == 'user' else 'Coach'}: "
            f"{turn.get('text', '').strip()}"
            for turn in recent
            if turn.get("text")
        ]

        if not lines:

            return ""

        return (
            "\nÚLTIMOS TURNOS DA CONVERSA (mais antigo → mais recente):\n"
            + "\n".join(lines)
            + "\n"
        )

    @staticmethod
    def _parse(raw: str) -> BrainDecision | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        if not isinstance(data, dict):

            return None

        say = str(data.get("say") or "").strip()

        card = data.get("answer_card")

        if card not in _CARDS:

            card = None

        on_pending = data.get("on_pending")

        if on_pending not in _ON_PENDING:

            on_pending = None

        action = CoachBrain._parse_action(data.get("action"))

        # precisa de ALGO acionável: uma fala, um cartão, uma ação ou um
        # veredito de pendência — senão não dá pra responder (cai no fallback)
        if not (say or card or action or on_pending):

            return None

        return BrainDecision(
            say=say,
            answer_card=card,
            action=action,
            on_pending=on_pending,
        )

    @staticmethod
    def _parse_action(raw) -> BrainAction | None:

        if not isinstance(raw, dict):

            return None

        action_type = raw.get("type")

        if action_type not in _ACTION_TYPES:

            return None

        scope = raw.get("scope")

        if scope not in _SCOPES:

            scope = "single_session"

        target_day = raw.get("target_day")

        if not isinstance(target_day, str) or not target_day.strip():

            target_day = None

        return BrainAction(
            type=action_type,
            scope=scope,
            target_day=target_day,
            instruction=str(raw.get("instruction") or "").strip(),
        )
