"""O atleta fala dos tênis em linguagem natural; aqui a IA (blindada) traduz pra
OPERAÇÕES estruturadas e a camada determinística APLICA — registrar par, definir
o do dia a dia, ensinar o rodízio, corrigir a atribuição, aposentar, ou só
consultar a km. Os NÚMEROS de km saem do armário (determinísticos), nunca da IA
(a IA só entende a intenção). Ver [[project_tracker_tenis]] e
[[feedback_ia_json_blindada]]."""

import json
import re
import unicodedata
from datetime import date

from google.genai import types

from app.core.config import get_settings
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.shoe import DEFAULT_WEAR_KM, Shoe, ShoeBook, ShoeRule
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)
from app.infrastructure.persistence.shoe_repository import ShoeRepository

_MAX_TOKENS = 500

_PROMPT = """Você interpreta o que {name} disse sobre os TÊNIS de corrida dele \
e devolve as operações pro sistema aplicar. NÃO invente km — o sistema tem os \
números; você só entende a INTENÇÃO.

TÊNIS QUE ELE JÁ TEM (id | nome | apelido | dia-a-dia?):
{shoes}

REGRAS DE RODÍZIO JÁ CADASTRADAS:
{rules}

Devolva UM JSON:
{{"reply": "<1 frase curta na voz do coach reconhecendo o que ele disse; NÃO \
cite números de km>",
  "ops": [
    {{"op": "add", "name": "<o nome EXATAMENTE como o atleta escreveu — só ajuste \
maiúsculas; NUNCA troque a marca, expanda ou adivinhe o modelo oficial (ex.: \
'evo sl branco' fica 'Evo SL Branco', NÃO vira 'Puma Deviate')>", \
"nickname": "<apelido curto|null>", \
"category": "<prova|dia a dia — INFIRA pelo modelo (veja abaixo)>", \
"initial_km": <km que o par já rodou antes, número|0>, "default": <true no par de \
treino/rodagem mais versátil>, "threshold_km": <vida útil típica do MODELO em km \
— placa de carbono ~450, trainer de rodagem ~650, max-cushion ~800; se ele disser \
um valor, use o dele; null se não reconhecer o modelo>}},
    {{"op": "set_default", "shoe": "<id ou nome de um tênis existente>"}},
    {{"op": "rule", "match": "<palavra do tipo de treino: tiro|longao|prova|\
rodagem|...>", "shoe": "<id/nome>"}},
    {{"op": "retire", "shoe": "<id/nome>"}},
    {{"op": "threshold", "shoe": "<id/nome>", "km": <número>}},
    {{"op": "correct_last", "shoe": "<id/nome>"}}
  ],
  "show_status": <true se ele PERGUNTOU a km/quantos km, ou se vale mostrar o \
resumo depois de registrar>}}

COMO MAPEAR:
- "meus tênis são A e B", "corro com um X", "comprei um Y" -> uma op "add" por \
par. Se cita km que o par já tem ("o Boston já tem 200km"), põe em initial_km.
- VOCÊ ENCAIXA a função de cada par pelo MODELO — o atleta NÃO precisa dizer "uso \
X no tiro". RECONHEÇA o modelo mesmo escrito informal/abreviado (ex.: "evo sl" = \
Adidas Adizero Evo SL; "red hare" = Li-Ning Red Hare; "clifton" = Hoka Clifton). \
Você é o coach, sabe pra que serve cada tênis: modelo de PLACA DE CARBONO / \
competição / racing (Vaporfly, Alphafly, Adios Pro, Metaspeed, Endorphin Pro, \
Deviate, Red Hare, Cielo, etc.) -> category="prova" (tiros/tempo/prova). Tênis de \
TREINO/rodagem amortecido (Boston, Pegasus, Ghost, Rider, Clifton, Cumulus, \
Novablast, Vomero, etc.) -> category="dia a dia". IMPORTANTE: se você NÃO tiver \
CERTEZA da função do modelo, deixe category=null (o sistema busca na web e \
classifica com precisão) — NÃO chute "dia a dia". Marque default=true no tênis de \
"dia a dia" mais versátil (se ele não disser qual, escolha você).
- "meu tênis do dia a dia agora é o Z", "troquei pro novo", "o de sempre é o W" \
-> "set_default".
- SÓ crie "rule" quando ele CORRIGIR/insistir num rodízio diferente do óbvio \
("na verdade uso o Vaporfly até na rodagem", "longão eu faço com o X"). O padrão \
é você encaixar pela categoria — não precisa de regra.
- "hoje/essa corrida foi com o de prova", "corri com o Vaporfly hoje" -> \
"correct_last" (corrige o ÚLTIMO treino).
- "aposentei o Boston", "esse tênis já era" -> "retire".
- "o Vaporfly aguenta só 400km", "esse dura 500" -> "threshold".
- "quanto tem meu tênis?", "quantos km no Boston?" -> ops=[] e show_status=true.
- Referencie tênis EXISTENTES por id ou nome como aparecem na lista acima. Só \
use "add" pra par NOVO (que não está na lista).

MENSAGEM DO ATLETA:
"{message}"
"""


class ShoeCommandEngine:

    @staticmethod
    async def handle(
        profile: str, runner: RunnerProfile, incoming_text: str
    ) -> str | None:

        repo = ShoeRepository()

        book = repo.load(profile)

        parsed = await ShoeCommandEngine._parse_command(
            runner.name, book, incoming_text
        )

        if parsed is None:

            # IA fora do ar / JSON impossível: não finge — devolve None e o
            # cérebro cai na fala/cascata
            return None

        reply = str(parsed.get("reply") or "").strip()

        ops = parsed.get("ops") or []

        show_status = bool(parsed.get("show_status"))

        existing_ids = {s.id for s in book.shoes}

        applied_any = False

        for op in ops:

            if ShoeCommandEngine._apply_op(book, op):

                applied_any = True

        # FALLBACK WEB: par NOVO que o coach não classificou (categoria vazia) ->
        # busca na web quem é o modelo e preenche função + vida útil. Só no caso
        # raro (modelo desconhecido); best-effort, nunca derruba o registro.
        enriched_any = await ShoeCommandEngine._enrich_unknown(book, existing_ids)

        if applied_any or enriched_any:

            repo.save(profile, book)

        # nada reconhecido e sem pergunta de status: deixa o cérebro conversar
        if not applied_any and not show_status and not reply:

            return None

        # os NÚMEROS saem do armário (exatos), nunca da IA
        if show_status or applied_any:

            status = ShoeCommandEngine._status_block(book)

            if status:

                reply = f"{reply}\n\n{status}" if reply else status

        return reply or None

    @staticmethod
    async def _enrich_unknown(book: ShoeBook, existing_ids: set) -> bool:
        """Pra cada par NOVO sem categoria (o coach não reconheceu o modelo),
        busca na web e preenche função + vida útil. Best-effort: falha vira
        no-op (o par fica no padrão, silencioso)."""

        from app.application.shoes.shoe_web_lookup import ShoeWebLookup

        changed = False

        for shoe in book.shoes:

            if shoe.id in existing_ids or shoe.category:

                continue

            try:

                info = await ShoeWebLookup.classify(shoe.name)

            except Exception as e:

                print(f"Busca web de tênis falhou p/ '{shoe.name}': {e}")

                info = None

            if not info:

                continue

            if info.get("category"):

                shoe.category = info["category"]

                changed = True

            if info.get("threshold_km"):

                shoe.alert_threshold_km = info["threshold_km"]

                changed = True

        return changed

    # ---- parsing (IA blindada) -------------------------------------------

    @staticmethod
    async def _parse_command(name: str, book: ShoeBook, message: str):

        settings = get_settings()

        prompt = _PROMPT.format(
            name=name,
            shoes=ShoeCommandEngine._shoes_context(book),
            rules=ShoeCommandEngine._rules_context(book),
            message=message.replace('"', "'"),
        )

        return await generate_json(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=_MAX_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=ShoeCommandEngine._parse_json,
        )

    @staticmethod
    def _parse_json(raw: str):

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        if not isinstance(data, dict):

            return None

        # precisa de algo: ops, status ou uma fala
        if not (data.get("ops") or data.get("show_status") or data.get("reply")):

            return None

        return data

    @staticmethod
    def _shoes_context(book: ShoeBook) -> str:

        if not book.active():

            return "(nenhum tênis cadastrado ainda)"

        return "\n".join(
            f"- {s.id} | {s.name} | {s.nickname or '-'} | "
            f"{'SIM' if s.is_default else 'não'}"
            for s in book.active()
        )

    @staticmethod
    def _rules_context(book: ShoeBook) -> str:

        if not book.rules:

            return "(nenhuma)"

        return "\n".join(f"- {r.match} -> {r.shoe_id}" for r in book.rules)

    # ---- aplicação determinística ----------------------------------------

    @staticmethod
    def _apply_op(book: ShoeBook, op: dict) -> bool:
        """Aplica UMA operação no armário. Devolve True se mudou algo."""

        if not isinstance(op, dict):

            return False

        kind = op.get("op")

        if kind == "add":

            return ShoeCommandEngine._add(book, op)

        if kind == "set_default":

            return ShoeCommandEngine._set_default(book, op.get("shoe"))

        if kind == "rule":

            return ShoeCommandEngine._add_rule(
                book, op.get("match"), op.get("shoe")
            )

        if kind == "retire":

            return ShoeCommandEngine._retire(book, op.get("shoe"))

        if kind == "threshold":

            return ShoeCommandEngine._threshold(book, op.get("shoe"), op.get("km"))

        if kind == "correct_last":

            return ShoeCommandEngine._correct_last(book, op.get("shoe"))

        return False

    @staticmethod
    def _add(book: ShoeBook, op: dict) -> bool:

        name = str(op.get("name") or "").strip()

        if not name:

            return False

        shoe_id = ShoeCommandEngine._unique_id(book, name)

        threshold = op.get("threshold_km")

        shoe = Shoe(
            id=shoe_id,
            name=name,
            nickname=(str(op.get("nickname")).strip()
                      if op.get("nickname") else None),
            category=(str(op.get("category")).strip()
                      if op.get("category") else None),
            initial_km=ShoeCommandEngine._num(op.get("initial_km")),
            alert_threshold_km=(
                ShoeCommandEngine._num(threshold) if threshold else DEFAULT_WEAR_KM
            ),
            created_at=date.today().isoformat(),
        )

        book.shoes.append(shoe)

        # é o do dia a dia? vira o único default
        if op.get("default"):

            ShoeCommandEngine._make_default(book, shoe)

        # primeiro tênis cadastrado sem ninguém marcado: assume o padrão
        elif not book.default():

            ShoeCommandEngine._make_default(book, shoe)

        return True

    @staticmethod
    def _set_default(book: ShoeBook, ref) -> bool:

        shoe = ShoeCommandEngine._resolve(book, ref)

        if shoe is None:

            return False

        ShoeCommandEngine._make_default(book, shoe)

        return True

    @staticmethod
    def _make_default(book: ShoeBook, shoe: Shoe) -> None:

        for s in book.shoes:

            s.is_default = s.id == shoe.id

    @staticmethod
    def _add_rule(book: ShoeBook, match, ref) -> bool:

        shoe = ShoeCommandEngine._resolve(book, ref)

        match = str(match or "").strip().lower()

        if shoe is None or not match:

            return False

        # dedup: mesma palavra -> reaponta pro par novo
        book.rules = [r for r in book.rules if r.match.lower() != match]

        book.rules.append(ShoeRule(match=match, shoe_id=shoe.id))

        return True

    @staticmethod
    def _retire(book: ShoeBook, ref) -> bool:

        shoe = ShoeCommandEngine._resolve(book, ref)

        if shoe is None:

            return False

        shoe.retired = True

        shoe.is_default = False

        return True

    @staticmethod
    def _threshold(book: ShoeBook, ref, km) -> bool:

        shoe = ShoeCommandEngine._resolve(book, ref)

        value = ShoeCommandEngine._num(km)

        if shoe is None or value <= 0:

            return False

        shoe.alert_threshold_km = value

        # subiu/mudou o limiar -> rearma o alerta (pode alertar de novo)
        shoe.wear_alerted = shoe.total_km >= value and shoe.wear_alerted

        return True

    @staticmethod
    def _correct_last(book: ShoeBook, ref) -> bool:
        """Move a km da ÚLTIMA corrida do par errado pro que o atleta indicou."""

        target = ShoeCommandEngine._resolve(book, ref)

        if target is None or book.last_shoe_id is None:

            return False

        if target.id == book.last_shoe_id:

            return False  # já está no par certo

        source = book.get(book.last_shoe_id)

        km = book.last_km

        if source is not None:

            source.accumulated_km = round(source.accumulated_km - km, 2)

            if book.last_activity_id in source.counted_ids:

                source.counted_ids.remove(book.last_activity_id)

        target.accumulated_km = round(target.accumulated_km + km, 2)

        if book.last_activity_id is not None:

            target.counted_ids.append(book.last_activity_id)

        book.last_shoe_id = target.id

        return True

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _resolve(book: ShoeBook, ref) -> Shoe | None:
        """Casa a referência da IA (id, apelido ou nome) com um tênis do
        armário. Prioriza id exato > apelido exato > nome (substring)."""

        needle = str(ref or "").strip().lower()

        if not needle:

            return None

        for s in book.shoes:

            if s.id.lower() == needle:

                return s

        for s in book.shoes:

            if s.nickname and s.nickname.lower() == needle:

                return s

        for s in book.shoes:

            if needle in s.name.lower() or s.name.lower() in needle:

                return s

        return None

    @staticmethod
    def _unique_id(book: ShoeBook, name: str) -> str:

        base = ShoeCommandEngine._slug(name) or "tenis"

        candidate = base

        n = 2

        existing = {s.id for s in book.shoes}

        while candidate in existing:

            candidate = f"{base}-{n}"

            n += 1

        return candidate

    @staticmethod
    def _slug(text: str) -> str:

        normalized = unicodedata.normalize("NFKD", text)

        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

        slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")

        return slug[:24]

    @staticmethod
    def _num(value) -> float:

        try:

            return round(float(value), 2)

        except (TypeError, ValueError):

            return 0.0

    @staticmethod
    def _status_block(book: ShoeBook) -> str:
        """Resumo com os km EXATOS do armário (nunca da IA)."""

        active = book.active()

        if not active:

            return ""

        lines = ["👟 Teus tênis:"]

        for s in active:

            tag = " · dia a dia" if s.is_default else ""

            wear = ""

            if s.total_km >= s.alert_threshold_km:

                wear = " ⚠️ hora do rodízio"

            lines.append(f"• {s.label}{tag}: {round(s.total_km)} km{wear}")

        return "\n".join(lines)
