import re
import unicodedata

from app.core.weekdays import WEEKDAYS

# Parser local do onboarding: resolve sem Gemini os passos de resposta
# previsível (sim/não, nome, números, dias). Cada passo devolve o mesmo
# formato de dict que o parser do Gemini — ou None quando a resposta é
# ambígua, e aí o fluxo cai no Gemini como fallback.
#
# Motivação: cada chamada ao Gemini no cadastro é um ponto único de falha
# ("me embananei") logo no primeiro contato do atleta, e queima cota do
# nível gratuito. Um "sim" não precisa de IA pra ser entendido.


def _norm(text: str) -> str:
    """minúsculas sem acento: casa "não"/"nao", "terça"/"terca"."""

    decomposed = unicodedata.normalize("NFKD", text.lower())

    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )


# ==========================================================
# Sim / Não
# ==========================================================

_NEG_PATTERNS = (
    r"\bnao\b",
    r"\bn\b",
    r"\bnunca\b",
    r"\bjamais\b",
    r"\bnegativo\b",
    r"\bnenhum\b",
    r"\bnops?\b",
)

_POS_PATTERNS = (
    r"\bsim\b",
    r"\bs\b",
    r"\btenho\b",
    r"\buso\b",
    r"\bclaro\b",
    r"\bpositivo\b",
    r"\baham\b",
    r"\bisso\b",
    r"\bobvio\b",
    r"\bja\b",
    r"\byes\b",
    r"\bpossuo\b",
    r"\bbora\b",
    r"\bcerteza\b",
    r"\bpode\b",
    r"\bconfirmo\b",
)


def _yes_no(text: str) -> bool | None:
    """Negação tem prioridade ("não tenho" = não, mesmo contendo "tenho")."""

    normalized = _norm(text)

    if any(re.search(pattern, normalized) for pattern in _NEG_PATTERNS):

        return False

    if any(re.search(pattern, normalized) for pattern in _POS_PATTERNS):

        return True

    return None


def _yn(text: str, key: str) -> dict | None:

    value = _yes_no(text)

    return None if value is None else {key: value}


# ==========================================================
# ASK_NAME
# ==========================================================

# palavras de enrolação que antecedem o nome ("meu nome é Renato")
_NAME_STOPWORDS = {
    "meu", "nome", "e", "me", "chamo", "pode", "chamar", "de", "sou",
    "o", "a", "eu", "aqui", "ola", "oi", "opa", "boa", "prazer",
}

_NAME_WORD = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]*")


def _name(text: str) -> dict | None:

    words = [word for word in re.split(r"\s+", text.strip()) if word]

    # descarta enrolação inicial ("sou o", "meu nome é"...)
    while words and _norm(words[0]).strip(",.!:") in _NAME_STOPWORDS:

        words.pop(0)

    cleaned = [word.strip(",.!:") for word in words]

    cleaned = [word for word in cleaned if word]

    if 1 <= len(cleaned) <= 2 and all(
        _NAME_WORD.fullmatch(word) for word in cleaned
    ):

        return {"name": " ".join(cleaned)}

    return None


# ==========================================================
# ASK_AGE / ASK_WEIGHT / ASK_HEIGHT (uma medida por vez)
# ==========================================================


def _age(text: str) -> dict | None:

    normalized = _norm(text)

    labeled = re.search(r"(\d{1,3})\s*anos?", normalized)

    if labeled:

        return {"age": int(labeled.group(1))}

    # número solto só é aceito se for o único da mensagem
    bare = re.findall(r"\d{1,3}", normalized)

    if len(bare) == 1 and 10 <= int(bare[0]) <= 100:

        return {"age": int(bare[0])}

    return None


def _weight(text: str) -> dict | None:

    normalized = _norm(text)

    labeled = re.search(
        r"(\d{2,3}(?:[.,]\d+)?)\s*(?:kg|quilos?|kilos?)",
        normalized,
    )

    if labeled:

        return {"weight": float(labeled.group(1).replace(",", "."))}

    bare = re.findall(r"\d{2,3}(?:[.,]\d+)?", normalized)

    if len(bare) == 1:

        value = float(bare[0].replace(",", "."))

        if 30 <= value <= 250:

            return {"weight": value}

    return None


def _height(text: str) -> dict | None:

    normalized = _norm(text)

    # metros: "1,78", "1.78", "1,78 m"
    meters = re.search(r"\b([12])[.,](\d{1,2})\b", normalized)

    if meters:

        return {"height": float(f"{meters.group(1)}.{meters.group(2)}")}

    # centímetros: "178", "178 cm" -> metros
    centimeters = re.search(r"\b(1\d{2}|2[0-2]\d)\s*(?:cm)?\b", normalized)

    if centimeters:

        return {"height": int(centimeters.group(1)) / 100}

    return None


# ==========================================================
# ASK_RUNS_TODAY / ASK_RUNS_PER_WEEK / ASK_TYPICAL_KM
# ==========================================================

_NON_RUNNER_MARKERS = (
    "nao corro",
    "nao pratico",
    "nao costumo",
    "nunca corri",
    "iniciante",
    "comecando agora",
    "nao faco",
    "nao treino",
)


def _runs_today(text: str) -> dict | None:

    answer = _yes_no(text)

    if answer is not None:

        return {"runs_today": answer}

    # "sou iniciante", "não corro ainda": sem sim/não explícito
    if any(marker in _norm(text) for marker in _NON_RUNNER_MARKERS):

        return {"runs_today": False}

    return None


def _runs_per_week(text: str) -> dict | None:

    normalized = _norm(text)

    labeled = re.search(r"(\d)\s*(?:x|vezes|vez)", normalized)

    if labeled:

        return {"runs_per_week": int(labeled.group(1))}

    bare = re.findall(r"\d", normalized)

    if len(bare) == 1 and 1 <= int(bare[0]) <= 7:

        return {"runs_per_week": int(bare[0])}

    return None


def _typical_km(text: str) -> dict | None:

    normalized = _norm(text)

    labeled = re.search(r"(\d+(?:[.,]\d+)?)\s*km", normalized)

    if labeled:

        return {"typical_km": float(labeled.group(1).replace(",", "."))}

    bare = re.findall(r"\d+(?:[.,]\d+)?", normalized)

    if len(bare) == 1:

        value = float(bare[0].replace(",", "."))

        if 0 < value <= 50:

            return {"typical_km": value}

    return None


# ==========================================================
# ASK_PACE (tempo total na distância habitual, em minutos)
# ==========================================================


def _pace(text: str) -> dict | None:

    normalized = _norm(text)

    if "meia hora" in normalized:

        return {"typical_minutes": 30.0}

    hour = re.search(r"(\d+(?:[.,]\d+)?)\s*h(?:ora)?", normalized)

    if hour and "min" not in normalized:

        return {"typical_minutes": float(hour.group(1).replace(",", ".")) * 60}

    minutes = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:min|minuto)", normalized)

    if minutes:

        return {"typical_minutes": float(minutes.group(1).replace(",", "."))}

    clock = re.search(r"\b(\d{1,3}):(\d{2})\b", normalized)

    if clock:

        return {
            "typical_minutes": int(clock.group(1)) + int(clock.group(2)) / 60,
        }

    # número solto só é aceito se for o único da mensagem (sem ambiguidade)
    bare = re.findall(r"\b\d{1,3}\b", normalized)

    if len(bare) == 1 and 5 <= int(bare[0]) <= 300:

        return {"typical_minutes": float(bare[0])}

    return None


# ==========================================================
# ASK_DAYS
# ==========================================================

_DAY_FULL = {
    "segunda": "Monday",
    "terca": "Tuesday",
    "quarta": "Wednesday",
    "quinta": "Thursday",
    "sexta": "Friday",
    "sabado": "Saturday",
    "domingo": "Sunday",
}

_DAY_ABBR = {
    "seg": "Monday",
    "ter": "Tuesday",
    "qua": "Wednesday",
    "qui": "Thursday",
    "sex": "Friday",
    "sab": "Saturday",
    "dom": "Sunday",
}


def _days(text: str) -> dict | None:

    normalized = _norm(text)

    if any(
        marker in normalized
        for marker in ("todo dia", "todos os dias", "diariamente")
    ):

        return {"days": list(WEEKDAYS.values())}

    found: list[str] = []

    if any(
        marker in normalized
        for marker in ("final de semana", "fim de semana", "fds")
    ):

        found += ["Saturday", "Sunday"]

    # nome completo por substring ("terça-feira" contém "terca")
    for word, english in _DAY_FULL.items():

        if word in normalized:

            found.append(english)

    # abreviação só como token isolado ("seg", "qui")
    for word, english in _DAY_ABBR.items():

        if re.search(rf"\b{word}\b", normalized):

            found.append(english)

    days = list(dict.fromkeys(found))

    return {"days": days} if days else None


# ==========================================================
# ASK_WEEK_CHOICE (esta vs próxima semana)
# ==========================================================

_NEXT_MARKERS = (
    "proxima",
    "que vem",
    "semana que vem",
    "cheia",
    "segunda",
)

_CURRENT_MARKERS = (
    "esta",
    "essa",
    "atual",
    "agora",
    "nesta",
    "nessa",
    "ja",
)


def _week_choice(text: str) -> dict | None:

    normalized = _norm(text)

    is_next = any(marker in normalized for marker in _NEXT_MARKERS)

    is_current = any(
        re.search(rf"\b{marker}\b", normalized)
        for marker in _CURRENT_MARKERS
    )

    if is_next and not is_current:

        return {"start_week": "next"}

    if is_current and not is_next:

        return {"start_week": "current"}

    return None


# ==========================================================
# AWAIT_PLAN_MEDIA ("mando depois")
# ==========================================================

_SKIP_MARKERS = (
    "mando depois",
    "depois",
    "mais tarde",
    "agora nao",
    "nao tenho agora",
    "nao tenho aqui",
    "nao esta comigo",
    "outra hora",
    "nao tenho em maos",
)


def _skip(text: str) -> dict | None:

    normalized = _norm(text)

    if any(marker in normalized for marker in _SKIP_MARKERS):

        return {"skip": True}

    return None


# ==========================================================
# Despacho
# ==========================================================

_HANDLERS = {
    "ASK_NAME": _name,
    "ASK_AGE": _age,
    "ASK_WEIGHT": _weight,
    "ASK_HEIGHT": _height,
    "ASK_STRAVA": lambda text: _yn(text, "has_strava"),
    "ASK_RUNS_TODAY": _runs_today,
    "ASK_RUNS_PER_WEEK": _runs_per_week,
    "ASK_TYPICAL_KM": _typical_km,
    "ASK_COACH": lambda text: _yn(text, "has_coach"),
    "AWAIT_PLAN_MEDIA": _skip,
    "ASK_PACE": _pace,
    "ASK_DAYS": _days,
    "ASK_WEEK_CHOICE": _week_choice,
    "CONFIRM": lambda text: _yn(text, "confirmed"),
    # ASK_GOAL fica só no Gemini: prova/tempo/data pedem interpretação.
}


class DeterministicOnboardingParser:

    @staticmethod
    def parse(step: str, answer: str) -> dict | None:
        """Resposta interpretada localmente, ou None se ambígua (o fluxo
        cai no Gemini)."""

        handler = _HANDLERS.get(step)

        if handler is None:

            return None

        if not answer or not answer.strip():

            return None

        return handler(answer)
