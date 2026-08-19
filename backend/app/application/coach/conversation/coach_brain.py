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
from dataclasses import dataclass, field

from google.genai import types

from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# dias válidos em minúsculo -> forma canônica ("saturday" -> "Saturday"), pra
# blindar o casing que o Gemini varia (ora "Sunday", ora "saturday") antes de
# chegar aos appliers/engines, que esperam o inglês canônico.
_CANON_DAY = {name.lower(): name for name in WEEKDAYS.values()}

# cartões EXATOS que o coach pode escolher pra responder (o dado sai
# determinístico, o coach só decide QUAL mostrar). Espelham os ChatIntent.
_CARDS = {
    "weekly_plan", "next_training", "last_training", "body", "fitness",
    "paces", "sleep", "race", "portrait", "help",
}

_ACTION_TYPES = {
    "move", "skip", "adjust", "simplify", "one_off", "routine", "goal",
    "preference",
}

_SCOPES = {"single_session", "week"}

_ON_PENDING = {"apply", "reject", "refine"}

MAX_OUTPUT_TOKENS = 700


PROMPT_TEMPLATE = """Você é o COACH de corrida do Ritmind, conversando por \
WhatsApp com {runner_name}. Você é UM coach só, que CONHECE o atleta — tem o \
histórico, os treinos, o corpo e as preferências dele no QUADRO abaixo. Toda \
resposta é SUA, na sua voz de treinador (direta, cordial, sem markdown).

FORMATO (WhatsApp/Telegram): nada de markdown (**, ##, listas numeradas saem \
crus). Quando descrever um TREINO com blocos (aquecimento / parte principal / \
desaquecimento) ou qualquer lista de passos, coloque CADA bloco em SUA PRÓPRIA \
LINHA começando com "•" (quebra de linha real entre eles) — NUNCA enfie os \
blocos num parágrafo corrido, que vira um paredão ilegível. Um recado curto \
segue em texto normal. Emoji com moderação.

QUADRO COMPLETO DO ATLETA (fatos determinísticos — use SÓ estes números, nunca \
invente nem arredonde):
{context_facts}
{pending_block}
Decida a MELHOR reação à mensagem do atleta e devolva UM JSON:

{{"say": "sua resposta ao atleta, na voz do coach",
  "answer_card": <um de: {cards} | null>,
  "actions": [] | [{{"type": <move|skip|adjust|simplify|one_off|routine|goal|\
preference>,
                     "scope": <single_session|week>,
                     "target_day": <dia em inglês|null>,
                     "instruction": "o que mudar, em 1 frase",
                     "content_change": <se ALÉM de mover o dia ele também quer o \
treino diferente, o que muda no CONTEÚDO | null>}}, ...],
  "on_pending": null | <apply|reject|refine>}}

COMO ESCOLHER:
- Pergunta com DADO DENSO/EXATO (o plano da semana, o próximo treino, os paces/\
zonas, leitura de corpo, sono, evolução, estratégia de prova, o último treino, \
ajuda): preencha "answer_card" com o cartão certo — o sistema renderiza o dado \
EXATO. Ainda escreva um "say" curto na sua voz introduzindo (ex.: "Bora ver teu \
plano 👇"). "qual o treino de amanhã?" = next_training; "meu plano da semana" = \
weekly_plan; "meus paces/zonas" = paces; "como tá meu corpo" = body; "vou \
bater minha meta? / tô no ritmo da prova? / estratégia da prova" = race.
- ADAPTAR/EXECUTAR um treino que o atleta JÁ TEM ("como faço na esteira?", \
"como executo esse treino?", "adapta pra chuva/rua", "como corro isso?"): \
responda NO "say" com os blocos JÁ adaptados (cada bloco em sua linha com "•", \
usando os números exatos do quadro) e deixe "answer_card"=null — ele já tem o \
treino, o cartão só REPETIRIA a sessão embaixo (paredão). answer_card=\
next_training é só pra quando ele pergunta QUAL é o treino, não COMO fazê-lo.
- Pedido de MUDAR o plano SÓ DESTA SEMANA (mover de dia, pular, deixar mais \
leve/livre, simplificar pro relógio, trocar tipo, mudar objetivo, fixar dia do \
longão): coloque em "actions". ESCOPO é sagrado — se o atleta aponta UMA sessão \
("o de amanhã", "só o longão"), scope="single_session" e target_day daquele \
dia; se fala da semana, scope="week". NUNCA mexa em mais do que ele pediu. Se \
ele muda o DIA de um treino (de X pra Y), o type é "move" e o target_day é o \
DESTINO. Se ALÉM de mudar o dia ele também quer o treino diferente ("passa o \
longão pra sábado e deixa livre pra somar km"), continua type="move" + \
target_day=destino E preencha "content_change" com o que muda no conteúdo — o \
sistema faz as duas coisas numa proposta só. Deixar mais leve/livre/sem pace \
SEM trocar de dia = "simplify" ou "adjust". NÃO aplique agora — o sistema monta \
a proposta e pergunta "posso aplicar?". No "say", reconheça o pedido.
- MAIS DE UMA MUDANÇA na mesma mensagem: coloque CADA uma como um item \
SEPARADO em "actions". Ex.: "troca meu treino de terça pra quarta E o de quinta \
pra sexta" = DOIS itens move (um por troca, cada um com seu target_day). \
"deixa terça mais leve e move quinta pra sexta" = um "adjust"/"simplify" de \
terça + um "move" de quinta. O sistema aplica TODAS numa proposta só. Uma \
mudança = lista de 1 item; nenhuma mudança de plano = []. NUNCA deixe uma \
mudança pedida de fora da lista — se o atleta citou duas, "actions" tem duas.
- Pedido pra MONTAR um treino NOVO num dia que o plano NÃO cobre ("monta um \
treino pra domingo", "quero um treino pra hoje", "me dá um treino pra amanhã" \
num dia sem treino): type="one_off" + target_day. É montar do zero, não mover \
nem ajustar uma sessão existente. No "say", reconheça (o sistema monta a sessão \
ancorada no histórico e oferece o relógio).
- Pedido DURÁVEL de rotina, pra valer DAQUI PRA FRENTE e não só nesta semana \
("a partir da próxima, treinos de semana em até 50 min", "fim de semana sempre \
sem pressa", "de agora em diante deixa terça mais curta"): type="routine". Isso \
vira uma PREFERÊNCIA na memória do atleta que molda os PRÓXIMOS planos — NÃO \
mexe na semana atual. Só use "routine" quando houver horizonte/durabilidade ("a \
partir de", "sempre", "toda semana", "de agora em diante", "no geral"); um \
pedido pra mexer só na semana de agora é "adjust"/"simplify", não "routine". No \
"say", uma confirmação curta de que entendeu e vai montar os próximos assim.
- Se há PROPOSTA PENDENTE (bloco acima): a mensagem é a resposta a ela. \
"on_pending"="apply" se ele aceitou; "reject" se recusou; "refine" se está \
CORRIGINDO ("não é a semana, é o de amanhã", "sim mas 12km") — no refine, \
preencha TAMBÉM "actions" com a versão corrigida (escopo certo).
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

    # quando o pedido é composto (mover de dia E mudar o conteúdo do treino),
    # carrega o que muda no CONTEÚDO — o executor faz as duas coisas numa
    # proposta só. None quando é só mover (ou qualquer outra ação).
    content_change: str | None = None


@dataclass(slots=True)
class BrainDecision:

    say: str

    answer_card: str | None = None

    # ação ÚNICA (compat com chamadas antigas/testes que passam `action=`); o
    # caminho vivo usa a LISTA `actions` (pedido pode ter várias mudanças).
    action: BrainAction | None = None

    actions: list[BrainAction] = field(default_factory=list)

    on_pending: str | None = None

    @property
    def all_actions(self) -> list[BrainAction]:
        """As ações a executar — a lista quando há; senão a única (compat)."""

        if self.actions:

            return self.actions

        return [self.action] if self.action else []


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

        actions = CoachBrain._parse_actions(data)

        # precisa de ALGO acionável: uma fala, um cartão, uma ação ou um
        # veredito de pendência — senão não dá pra responder (cai no fallback)
        if not (say or card or actions or on_pending):

            return None

        return BrainDecision(
            say=say,
            answer_card=card,
            actions=actions,
            on_pending=on_pending,
        )

    @staticmethod
    def _parse_actions(data: dict) -> list[BrainAction]:
        """Lê a LISTA de ações. Aceita o `actions` novo (lista) e, por
        robustez, o `action` singular antigo (o Gemini pode hesitar) — cada um
        vira BrainAction; itens inválidos são descartados."""

        raw = data.get("actions")

        items = raw if isinstance(raw, list) else []

        # compat: modelo ainda pode mandar "action" singular
        if not items and data.get("action") is not None:

            items = [data.get("action")]

        parsed = []

        for item in items:

            action = CoachBrain._parse_action(item)

            if action is not None:

                parsed.append(action)

        return parsed

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

        else:

            target_day = _CANON_DAY.get(target_day.strip().lower(), target_day)

        content_change = raw.get("content_change")

        if not isinstance(content_change, str) or not content_change.strip():

            content_change = None

        return BrainAction(
            type=action_type,
            scope=scope,
            target_day=target_day,
            instruction=str(raw.get("instruction") or "").strip(),
            content_change=content_change,
        )
