import json
from datetime import date

from google.genai import types

from app.core.clock import today_local
from app.core.config import get_settings
from app.domain.entities.memory_entry import (
    MEMORY_CATEGORIES,
    MemoryEntry,
)
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

MAX_OUTPUT_TOKENS = 400

EMPTY_OPS: dict = {"add": [], "archive": []}

_WEEKDAYS_PT = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)

EXTRACTION_PROMPT_TEMPLATE = """Você mantém a memória de longo prazo do coach \
de corrida do Ritmind sobre o corredor {runner_name}.

Hoje é {today} ({weekday}) — use para resolver datas relativas como "em agosto", \n"terça que vem", "daqui a 7 dias".

Analise a MENSAGEM NOVA do corredor e decida se ela contém fatos duráveis que
o coach deve lembrar em conversas futuras. Categorias possíveis:
- lesao: lesão ou dor MUSCULOESQUELÉTICA que afeta/limita a corrida — joelho,
  canela (canelite), tornozelo, quadril, coluna, muscular (estiramento),
  tendão (tendinite), fascite etc. É um LIMITE físico da mecânica de correr.
  NÃO é doença passageira: gripe, resfriado, virose, febre, dor de garganta,
  catarro, tosse, covid, sinusite, indisposição — NADA disso é "lesao" (vai em
  "vida"). Na dúvida entre lesão e doença, NÃO marque como lesao.
- preferencia: preferências de treino (horário, terreno, tipo de treino...) —
  MAS veja a regra "DIA DE QUALIDADE" abaixo antes de cravar um tipo de treino
- disponibilidade: viagens, ausências, mudanças de agenda
- objetivo: mudança de meta ou prova alvo
- motivacao: o PORQUÊ profundo de correr / o que a corrida significa pra ele /
  marcos de identidade (voltou depois de lesão, primeira vez sem parar, corre
  pela saúde após um susto, por alguém, pra provar algo, pra aliviar o stress).
  SÓ quando ele REVELA de verdade — nunca invente nem deduza um "porquê".
- vida: evento de vida relevante ao treino, INCLUSIVE doença passageira (gripe,
  resfriado, virose, febre, catarro...), trabalho puxado, sono, stress
- outro: fato durável que não se encaixa acima

MEMÓRIAS ATIVAS ATUAIS (id — [categoria] conteúdo):
{current_memories}

ÚLTIMAS MENSAGENS DA CONVERSA (contexto):
{recent_turns}

MENSAGEM NOVA DO CORREDOR:
{incoming_text}

Responda APENAS com JSON neste formato:
{{"add": [{{"category": "...", "content": "...", "until": "AAAA-MM-DD ou null"}}], \n"archive": ["id"]}}

PROVA ALVO (opcional): se a mensagem definir ou mudar uma prova alvo do
corredor (distância e/ou data), inclua também:
"race": {{"name": "10 km", "date": "2026-08-15", "target_time": "00:50:00"}}
— campos desconhecidos: null; sem dia exato, use o dia 15 do mês citado.
Se disser que a prova foi cancelada ou já aconteceu:
"race": {{"clear": true}}

REGRAS:
- DIA DE QUALIDADE (NÃO engessar o tipo): a inteligência do treino é do COACH —
  ele decide o estímulo pensando na EVOLUÇÃO do atleta rumo à META. Quando o
  corredor liga um treino FORTE de velocidade a um dia (tiro, intervalado,
  fartlek, VO2, tempo/limiar — ex: "quero intervalado na terça"), NÃO cristalize
  o TIPO específico: guarde a INTENÇÃO — "terça é o dia do treino forte de
  qualidade/velocidade; o coach varia o tipo (intervalado/fartlek/VO2/tempo)
  semana a semana rumo à meta". Só fixe UM tipo exato se ele for ENFÁTICO que
  quer SEMPRE aquele e nenhum outro. Rodagem, longão e regenerativo são
  estímulos de base — esses podem ficar como ele disse.
- Só fatos duráveis. Perguntas, cumprimentos e comentários sobre um treino
  pontual NÃO geram memória.
- Pedido pra mexer SÓ num treino, num dia ou nesta semana ("passa o de hoje
  pra amanhã", "essa semana quinta não dá", "reorganiza por causa da prova de
  sábado") é AÇÃO do momento, NÃO memória. Dia/rotina só vira memória quando ele
  diz que vale DAQUI PRA FRENTE ("a partir de agora", "sempre", "toda semana",
  "meus dias são"). Senão uma troca de um dia vira regra e o plano passa a usar
  o dia errado (Maurício: "passa o de hoje pra sexta" virou "prefere sexta").
- Quando ele FIXA os dias/rotina de novo, ARQUIVE ("archive") as notas de dia
  antigas que a nova contradiz — a memória não pode ter duas verdades.
- "content" em uma linha curta, em português, terceira pessoa implícita
  (ex: "Dor no joelho direito").
- NÃO duplique memória ativa existente (nem com outras palavras).
- Se a mensagem indicar que um fato registrado se resolveu ou mudou
  (ex: "o joelho melhorou"), inclua o id correspondente em "archive".
- PRAZO ("until"): fato que TEM FIM — ausência, viagem, pausa/afastamento (inclusive
  por orientação médica), repouso, recuperação, "por N dias/semanas", "até X" —
  leva "until" = o ÚLTIMO dia em que ele vale (AAAA-MM-DD), contado a partir de
  hoje ({today}). Escreva o "content" com as DATAS (dd/mm) e o dia da volta, nunca
  só "por 7 dias" solto. Ex.: hoje 29/09 (terça), "vou ficar 7 dias sem treinar"
  → content "Sem treinar de 29/09 a 05/10 (7 dias, orientação médica); volta a
  treinar em 06/10", until "2026-10-05". Fato durável (preferência, objetivo,
  rotina): "until" null.
- PRAZO NOVO: se a mensagem, MESMO CURTA, fala da data de VOLTA de um fato ativo
  ("mas terça que vem voltamos", "só volto quinta", "vou ficar mais 3 dias"), o
  fato CONTINUA valendo até lá. Se o "content" ativo já traz essa data, NÃO faça
  nada (nem archive). Se a data mudou, ARQUIVE o antigo E ADICIONE o atualizado
  com o "until" novo. Só ARQUIVE sem adicionar quando ele já VOLTOU ou foi
  liberado AGORA ("o médico liberou", "já posso correr", "voltei"). Dizer que
  volta DEPOIS nunca encerra a ausência: arquivar aqui apaga a pausa dele da
  memória enquanto ele ainda está parado.
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
            weekday=_WEEKDAYS_PT[today_local().weekday()],
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
            MemoryExtractionEngine._clean_item(item)
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
    def _clean_item(item: dict) -> dict:
        """`until` só passa se for uma data ISO válida (a IA erra conta; o ciclo
        de vida ainda descarta prazo absurdo). Senão o item segue sem prazo e a
        rede do MemoryLifecycle deduz do texto."""

        until = item.get("until")

        if isinstance(until, str):

            try:

                date.fromisoformat(until[:10])

                return {**item, "until": until[:10]}

            except ValueError:

                pass

        return {k: v for k, v in item.items() if k != "until"}

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
