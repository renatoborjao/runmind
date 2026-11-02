"""LEMBRANÇA DA CONVERSA — o coach acha o que o atleta e ele já disseram, mesmo meses atrás.

O chat carregava as últimas turnas e um resumo; o resto (as mensagens que saíram da janela de 200, as
análises e planos que o coach mandou) ficava guardado no arquivo permanente mas ninguém LIA. Renato
(01/11): "o coach precisa ter visão de tudo; o histórico é super importante". Quando o atleta pergunta
"o que a gente combinou em julho?" ou "lembra do que eu falei do joelho?", o coach responde com o que
foi dito, não com o que supõe.

Busca LÉXICA (sem IA, sem custo, sem serviço externo): palavras de conteúdo normalizadas (sem acento,
sem artigos, no singular), peso maior pras palavras raras (idf), marcas de treino que ele cita ("10 km",
"sub-50"), filtro por período quando a mensagem cita ("em julho", "dia 15/08", "quando comecei"). Só
devolve quando há casamento de verdade (2+ palavras em comum, ou 1 bem rara, ou um período citado) —
mensagem curta ou comum ("bora", "valeu") não traz nada. Corpus = conversas vivas + arquivo permanente +
mensagens enviadas pelo coach (vivas + arquivo). Trechos LITERAIS e datados; o coach usa se ajudarem.
Puro/determinístico ([[feedback_ia_decide_sem_regras]])."""

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

# as últimas turnas o chat já carrega: não repetir
SKIP_RECENT = 16

TOP_K = 5

SNIPPET_CHARS = 230

REPLY_CHARS = 150

# "quando comecei", "no início": os primeiros dias da história dele com o coach
BEGINNING_DAYS = 45

# só período citado (sem palavra em comum): peso de cada papel e tamanho mínimo da fala do atleta
_ROLE_WEIGHT = {"atleta": 3.0, "coach": 1.5, "coach (mensagem enviada)": 0.1}
_MIN_SUBSTANCE = 30

# casamento mínimo sem período citado: 2 palavras de conteúdo em comum, ou 1 bem rara
_MIN_SHARED = 2
_RARE_DF = 3
_MIN_RARE_LEN = 6

_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

_STOPWORDS = frozenset("""
    para pelo pela pelos pelas como mais muito muita muitos muitas tambem entao porque quando onde
    qual quais quem aquele aquela aquilo esse essa esses essas isso este esta estes estas aqui ali
    voce voces gente falei falou falamos disse disseram lembra lembro lembrar combinamos combinou
    combinei sobre depois antes ainda sempre nunca todo toda todos todas cada outro outra outros
    tenho tinha temos tinhamos fazer fiz fez fizemos vamos vou vai foi ser sido estou estava
    estamos tudo nada algo alguma algum alguns umas uns nosso nossa nossos nossas meu minha meus
    minhas seu sua seus suas dele dela deles delas nele nela coisa coisas assim entre desde
    sem mesmo mesma pode posso podemos podia quero queria quer bom boa bem tipo vez vezes
    hoje ontem amanha dia dias semana semanas mes meses ano anos treino treinos corrida corridas
    correr corri coach nao sim obrigado obrigada valeu beleza comecei
""".split())

# marcas de treino que carregam sentido mesmo curtas: "10km", "21km", "sub50"
_MARK = re.compile(r"^(?:\d+km|sub\d+)$")

_BEGINNING = re.compile(
    r"\b(?:quando comecei|logo no comeco|no comeco|no inicio|primeira conversa|quando entrei|"
    r"quando cheguei)\b"
)


@dataclass(slots=True)
class Turn:

    day: date
    role: str                       # "atleta", "coach", "coach (mensagem enviada)"
    text: str
    stamp: str = ""                 # horário completo: ordena as turnas do mesmo dia


@dataclass(slots=True)
class Hit:

    turn: Turn
    reply: str | None
    score: float


def _normalize(text: str) -> str:

    lowered = (text or "").lower()

    return "".join(
        c for c in unicodedata.normalize("NFD", lowered) if unicodedata.category(c) != "Mn"
    )


def tokens(text: str) -> set[str]:
    """As palavras de CONTEÚDO: sem acento, 4+ letras, fora das palavras comuns, no singular. "10 km",
    "10k" e "sub-50" viram uma palavra só ("10km", "sub50") — marcas que o atleta cita e que a limpeza
    de palavras curtas apagaria."""

    norm = _normalize(text)

    norm = re.sub(r"\bsub[- ]?(\d+)", r"sub\1", norm)

    norm = re.sub(r"\b(\d+)\s*(?:km|k)\b", r"\1km", norm)

    out = set()

    for word in re.findall(r"[a-z0-9]+", norm):

        if _MARK.match(word):

            out.add(word)

            continue

        if len(word) < 4 or word.isdigit():

            continue

        if len(word) > 5 and word.endswith("s"):

            word = word[:-1]

        if word not in _STOPWORDS:

            out.add(word)

    return out


def date_window(text: str, today: date, first: date | None = None) -> tuple[date, date] | None:
    """O período que a mensagem cita: "em julho", "mês passado", "dia 15/08", "quando comecei" (os
    primeiros 45 dias da conversa, se `first` é conhecido). None se não cita."""

    norm = _normalize(text)

    if first is not None and _BEGINNING.search(norm):

        return first, first + timedelta(days=BEGINNING_DAYS)

    match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", norm)

    if match:

        day, month = int(match.group(1)), int(match.group(2))

        year = int(match.group(3)) if match.group(3) else today.year

        year += 2000 if year < 100 else 0

        try:

            center = date(year, month, day)

        except ValueError:

            return None

        if center > today and not match.group(3):

            center = center.replace(year=center.year - 1)

        return center - timedelta(days=3), center + timedelta(days=3)

    if re.search(r"\bmes passado\b", norm):

        first_of_month = today.replace(day=1)

        last_prev = first_of_month - timedelta(days=1)

        return last_prev.replace(day=1), last_prev

    for name, number in _MONTHS.items():

        if re.search(rf"\b{name}\b", norm):

            year = today.year if number <= today.month else today.year - 1

            start = date(year, number, 1)

            end = date(year + (number == 12), number % 12 + 1, 1) - timedelta(days=1)

            return start, end

    return None


_TEMPLATE_STARTS = ("🏃", "🩺", "🗓", "🏁", "⚖", "📅", "📈", "🎯 Rumo")


def _templated(text: str) -> bool:
    """Mensagem em formato pronto (plano da semana, leitura do corpo, parabéns pelo treino): começa
    com o emoji de cabeçalho do modelo ou tem a lista de dias."""

    stripped = (text or "").lstrip()

    return stripped.startswith(_TEMPLATE_STARTS) or "\n🔹" in stripped


def _day_of(stamp) -> date | None:

    try:

        return date.fromisoformat(str(stamp)[:10])

    except ValueError:

        return None


def load(profile: str) -> list[Turn]:
    """O corpus do atleta: conversas (vivas + arquivo) e mensagens enviadas pelo coach (vivas +
    arquivo), sem repetição, em ordem cronológica. Vazio em qualquer falha."""

    try:

        from app.infrastructure.persistence.coach_outbox_repository import CoachOutboxRepository
        from app.infrastructure.persistence.conversation_repository import ConversationRepository
        from app.infrastructure.persistence.permanent_archive import PermanentArchive

        conversations = ConversationRepository()

        outbox = CoachOutboxRepository()

        raw: list[tuple[dict, str]] = [(t, "conversa") for t in conversations.load(profile)]

        raw += [
            (e["record"], "conversa")
            for e in PermanentArchive.load(conversations.storage, "conversations", profile)
        ]

        raw += [(m, "enviada") for m in outbox._load(profile)]

        raw += [
            (e["record"], "enviada")
            for e in PermanentArchive.load(outbox.storage, "coach_outbox", profile)
        ]

        seen: set[tuple] = set()

        turns: list[Turn] = []

        for record, source in raw:

            text = (record.get("display_text") or record.get("text") or "").strip()

            day = _day_of(record.get("timestamp"))

            if not text or day is None:

                continue

            key = (str(record.get("timestamp")), text[:80])

            if key in seen:

                continue

            seen.add(key)

            if source == "enviada":

                role = "coach (mensagem enviada)"

            else:

                role = "atleta" if record.get("role") == "user" else "coach"

            turns.append(Turn(day, role, text, str(record.get("timestamp"))))

        return sorted(turns, key=lambda t: (t.day, t.stamp))

    except Exception as e:  # noqa: BLE001 — a lembrança nunca derruba o chat

        print(f"Lembrança da conversa falhou p/ '{profile}': {e}")

        return []


def search(
    turns: list[Turn], query: str, today: date, k: int = TOP_K, skip_recent: int = SKIP_RECENT,
) -> list[Hit]:
    """Os trechos antigos que casam com a mensagem. Pesa mais as palavras raras do corpus e, se a
    mensagem cita um período, só olha dentro dele. Vazio sem casamento de verdade."""

    wanted = tokens(query)

    window = date_window(query, today, turns[0].day if turns else None)

    if not wanted and window is None:

        return []

    pool = turns[:-skip_recent] if skip_recent and len(turns) > skip_recent else []

    if not pool:

        return []

    # a frequência de cada palavra no corpus inteiro: palavra rara pesa mais
    doc_freq: dict[str, int] = {}

    token_sets = [tokens(t.text) for t in pool]

    for words in token_sets:

        for word in words:

            doc_freq[word] = doc_freq.get(word, 0) + 1

    total = len(pool)

    scored: list[tuple[float, int]] = []

    for index, (turn, words) in enumerate(zip(pool, token_sets)):

        if window is not None and not (window[0] <= turn.day <= window[1]):

            continue

        shared = wanted & words

        weight = sum(math.log(1 + total / (1 + doc_freq[w])) for w in shared)

        rare = any(doc_freq[w] <= _RARE_DF and len(w) >= _MIN_RARE_LEN for w in shared)

        enough = len(shared) >= _MIN_SHARED or rare or any(_MARK.match(w) for w in shared)

        if window is None and not enough:

            continue

        if window is not None and not shared:

            # só o período, sem palavra em comum: vale o que foi CONVERSADO — o que o atleta disse
            # primeiro, a resposta do coach depois; a mensagem automática (plano, leitura, parabéns)
            # é modelo pronto e quase não conta
            if turn.role == "atleta" and len(turn.text) < _MIN_SUBSTANCE:

                continue

            weight = 0.01 * min(len(turn.text), 400) / 100 * _ROLE_WEIGHT[turn.role]

            # plano, leitura do corpo e afins que o coach manda na conversa são lista pronta: não é
            # o que foi combinado
            if _templated(turn.text):

                weight *= 0.05

        scored.append((weight, index))

    if not scored:

        return []

    best = sorted(scored, key=lambda item: (-item[0], -item[1]))[:k]

    hits = []

    for weight, index in sorted(best, key=lambda item: pool[item[1]].day):

        turn = pool[index]

        reply = None

        # a pergunta do atleta vem melhor com a resposta que o coach deu
        if turn.role == "atleta" and index + 1 < len(pool) and pool[index + 1].role == "coach":

            reply = pool[index + 1].text

        hits.append(Hit(turn, reply, round(weight, 2)))

    return hits


def _clip(text: str, limit: int) -> str:

    text = " ".join((text or "").split())

    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render(hits: list[Hit]) -> str:
    """O bloco pro prompt: trechos literais e datados. Vazio sem trecho."""

    if not hits:

        return ""

    lines = [
        "LEMBRANÇAS DA CONVERSA (trechos ANTIGOS, literais e datados, que casam com o que ele acabou "
        "de falar — do arquivo completo, fora das últimas mensagens):"
    ]

    for hit in hits:

        line = f"- {hit.turn.day:%d/%m/%y} ({hit.turn.role}): \"{_clip(hit.turn.text, SNIPPET_CHARS)}\""

        if hit.reply:

            line += f" → coach respondeu: \"{_clip(hit.reply, REPLY_CHARS)}\""

        lines.append(line)

    lines.append(
        "CONHECIMENTO, não regra: são o que foi dito na época. Use quando ajudar a responder com o que "
        "ele de fato falou ou combinou; se algo mudou desde então (meta, dias, saúde), o que está acima "
        "no quadro dele vale mais. Não force uma lembrança que não vem ao caso."
    )

    return "\n".join(lines)


def for_message(profile: str, incoming_text: str, today: date) -> str:
    """O bloco de lembranças pra mensagem que chegou. Vazio quando nada casa."""

    return render(search(load(profile), incoming_text, today))
