"""Roteador de AÇÃO por IA — a interação real com o coach.

Em vez de uma cascata de portões por palavra-chave (frágil: "mudar meu treino
DE domingo PARA amanhã" caía em "preferência de longão no domingo"), o coach LÊ
a mensagem inteira + contexto e decide O QUE o atleta pediu. Classifica em UMA
ação; o despacho reusa os fluxos/engines que já existem (que fazem a extração
fina e propõem, pedindo o 'sim').

Escopo: só MUTAÇÕES (mudar algo no plano/rotina/objetivo). Perguntas analíticas
("como foi meu treino", "meus paces") e respostas a pendências (sim/não, RPE,
voz) seguem no caminho determinístico rápido — não passam por aqui.

Blindagem ([[feedback_ia_json_blindada]]): saída estruturada + generate_json
(reparo/retry). Devolve None em falha (a IA fora do ar ou JSON torto) — o
chamador então cai na cascata determinística de hoje (nunca regride)."""

import json
from dataclasses import dataclass

from google.genai import types

from app.core.clock import today_local
from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS, weekday_label, weekday_name
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# ações de mutação que o coach sabe aplicar (cada uma tem um fluxo/engine)
_MOVE = "move"
_SKIP = "skip"
_ADJUST = "adjust"
_AVERSION = "aversion"
_PREFERENCE = "preference"
_GOAL = "goal"
_ONE_OFF = "one_off"
_NONE = "none"

_ACTIONS = {
    _MOVE, _SKIP, _ADJUST, _AVERSION, _PREFERENCE, _GOAL, _ONE_OFF, _NONE,
}

_VALID_DAYS = set(WEEKDAYS.values())

MAX_OUTPUT_TOKENS = 200

PROMPT_TEMPLATE = """Você é o treinador de corrida do Ritmind. Leia a mensagem \
do atleta {runner_name} e decida se ela é um PEDIDO DE MUDANÇA e de que TIPO. \
Não responda ao atleta — só classifique.

Hoje é {today}. Dias de treino do atleta: {days}.

MENSAGEM:
"{message}"

AÇÕES possíveis (escolha UMA, a que melhor traduz o PEDIDO PRINCIPAL):
- "move": quer FAZER um treino que já existe em OUTRO dia (tem origem e destino,
  ex.: "muda meu treino de domingo pra amanhã", "passa o de terça pra quarta").
- "skip": NÃO vai fazer um treino (pular/faltar/cancelar um dia).
- "adjust": quer a CARGA/volume da semana diferente (mais leve, mais pesado,
  menos km, mais rodagens) — sem ser um dia específico.
- "aversion": não gosta de um TIPO de treino (tiro, longão, intervalado) e quer
  evitar/trocar o TIPO.
- "preference": quer FIXAR de forma DURÁVEL o dia do longão ("prefiro/gosto do
  longão no domingo", "pode manter o longão no sábado"). NÃO é mover uma sessão
  desta semana. Preencha "long_run_day" com o dia (em inglês).
- "goal": quer mudar o OBJETIVO/meta/prova (distância, tempo-alvo, data).
- "one_off": quer que você MONTE um treino novo para um dia que o plano não
  cobre ("monta um treino pra domingo").
- "none": NÃO é pedido de mudança — pergunta, relato, dúvida, desabafo, conversa.

REGRAS:
- "mudar meu treino DE <dia> PARA <outro dia/amanhã/hoje>" é SEMPRE "move", nunca
  "preference" — o dia citado no "de" é a ORIGEM, não uma preferência.
- Na dúvida entre uma mutação e conversa, prefira "none" (o chat cuida).

Responda APENAS JSON:
{{"action": "move", "long_run_day": null}}
"""


@dataclass(slots=True)
class ActionDecision:

    action: str

    long_run_day: str | None = None


class CoachActionRouter:

    @staticmethod
    async def classify(
        runner: RunnerProfile,
        message: str,
    ) -> ActionDecision | None:
        """Classifica a mensagem numa ação de mutação (ou 'none'). Devolve None
        se a IA falhar/JSON vier torto — chamador cai na cascata determinística."""

        settings = get_settings()

        today = today_local()

        days = (
            ", ".join(
                weekday_label(d) for d in runner.preferred_running_days
            )
            or "não informados"
        )

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner.name,
            today=(
                f"{weekday_label(weekday_name(today))}, "
                f"{today.strftime('%d/%m/%Y')}"
            ),
            days=days,
            message=message.replace('"', "'"),
        )

        return await generate_json(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=CoachActionRouter._parse,
        )

    @staticmethod
    def _parse(raw: str) -> ActionDecision | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        if not isinstance(data, dict):

            return None

        action = data.get("action")

        if action not in _ACTIONS:

            return None

        long_run_day = data.get("long_run_day")

        if long_run_day not in _VALID_DAYS:

            long_run_day = None

        return ActionDecision(action=action, long_run_day=long_run_day)
