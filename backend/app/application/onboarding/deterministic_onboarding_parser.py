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

    # FAIXA primeiro ("5 a 15", "5-15km", "entre 5 e 15", "de 5 a 15"):
    # o atleta que corre entre X e Y não faz nem sempre X nem sempre Y —
    # usamos a MÉDIA como distância típica (senão "5 a 15km" virava 15,
    # inflando o volume semanal e o plano — bug da Fernanda). Guardamos os
    # extremos pra o contexto saber que a rodagem dele VARIA.
    faixa = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:a|-|—|ate|até|e)\s*(\d+(?:[.,]\d+)?)",
        normalized,
    )

    if faixa:

        low = float(faixa.group(1).replace(",", "."))

        high = float(faixa.group(2).replace(",", "."))

        if low > high:

            low, high = high, low

        avg = round((low + high) / 2, 1)

        if 0 < avg <= 50:

            return {
                "typical_km": avg,
                "typical_km_min": low,
                "typical_km_max": high,
            }

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

# posição de cada dia (0=segunda … 6=domingo), para expandir intervalos
_DAY_INDEX = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "domingo": 6,
    "seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6,
}

_DAY_TOKEN = "|".join(_DAY_INDEX)

# intervalo entre dois dias: "segunda a sexta", "de seg à sex",
# "segunda até sexta", "seg-sex". O conector "e" NÃO entra aqui de
# propósito — "segunda e sexta" são só esses dois dias, não o intervalo.
_DAY_RANGE = re.compile(
    rf"\b({_DAY_TOKEN})\b\s*(?:a|ate|ao|-|/)\s*\b({_DAY_TOKEN})\b"
)

# forma ordinal comum no Brasil: "2ª feira" = segunda … "6ª feira" = sexta.
# _norm já transforma "ª" em "a" (NFKD), então casamos "2a", "3a"… "6a".
# Exige o sufixo "a" de propósito: "5" solto NÃO é quinta (evita confundir
# com quem responde "5" pensando em "5 dias por semana").
_ORDINAL = {
    "2": "segunda", "3": "terca", "4": "quarta", "5": "quinta", "6": "sexta",
}

_ORDINAL_RE = re.compile(r"\b([2-6])a(?:\s*feira)?\b")


def _expand_ordinals(normalized: str) -> str:
    """Reescreve "2a"/"2a feira" como "segunda", pra reusar a lógica de
    lista e de intervalo ("2a a 6a" vira "segunda a sexta")."""

    return _ORDINAL_RE.sub(
        lambda match: f" {_ORDINAL[match.group(1)]} ",
        normalized,
    )


def _days(text: str) -> dict | None:

    normalized = _expand_ordinals(_norm(text))

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

    # intervalo "segunda a sexta": expande todos os dias entre as pontas
    for start, end in _DAY_RANGE.findall(normalized):

        low, high = sorted((_DAY_INDEX[start], _DAY_INDEX[end]))

        found += [WEEKDAYS[index] for index in range(low, high + 1)]

    # nome completo por substring ("terça-feira" contém "terca")
    for word, english in _DAY_FULL.items():

        if word in normalized:

            found.append(english)

    # abreviação só como token isolado ("seg", "qui")
    for word, english in _DAY_ABBR.items():

        if re.search(rf"\b{word}\b", normalized):

            found.append(english)

    # dedup preservando a ordem da semana (segunda → domingo)
    days = [day for day in WEEKDAYS.values() if day in found]

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
# CONFIRM_DAYS / CONFIRM (sim/não OU correção na conferência)
# ==========================================================

# pistas de que o atleta está corrigindo, não confirmando ("na verdade
# corro seg a sex"). Um único dia solto só conta como correção com uma
# dessas pistas — assim "pode sim, começando segunda" segue como "sim".
_CORRECTION_CUES = (
    "na verdade",
    "corrig",
    "errad",
    "errei",
    "mud",
    "troc",
    "posso correr",
    "consigo correr",
    "quero correr",
    "prefiro",
    "seria",
)

# rótulos/unidades que indicam correção de OUTRO campo do resumo (peso,
# idade, altura, nome, objetivo). Quando aparecem no CONFIRM, o determinístico
# se cala (retorna None) e deixa o Gemini extrair o campo — nunca deve ler um
# "sim" solto e finalizar com um dado que o atleta acabou de corrigir.
_FIELD_SIGNAL_MARKERS = (
    "kg",
    "quilo",
    "peso",
    "pesa",
    "anos",
    "idade",
    "altura",
    "cm",
    "metro",
    "nome",
    "chamo",
    "objetivo",
    "meta",
    "prova",
    "maratona",
    "km",
)

# altura em metros ("1,90" / "1.90"): sinal de correção de altura
_METER_RE = re.compile(r"\b[12][.,]\d")


def _days_correction(text: str) -> list[str] | None:
    """Reescrita de dias na conferência: 2+ dias (ou intervalo), ou 1 dia
    com pista de correção. Devolve a lista, ou None se não for correção."""

    parsed_days = _days(text)

    if not parsed_days:

        return None

    days = parsed_days["days"]

    has_cue = any(cue in _norm(text) for cue in _CORRECTION_CUES)

    if len(days) >= 2 or has_cue:

        return days

    return None


def _confirm_days_only(text: str) -> dict | None:
    """CONFIRM_DAYS: só dias importam aqui — reescrita de dias tem prioridade
    sobre o sim/não."""

    days = _days_correction(text)

    if days is not None:

        return {"corrections": {"days": days}}

    return _yn(text, "confirmed")


def _confirm_summary(text: str) -> dict | None:
    """CONFIRM (resumo completo): dias saem no determinístico; sinais de
    correção de outros campos (kg, anos, altura, objetivo...) caem no Gemini
    pra extração estruturada, mesmo que a frase contenha um "sim"."""

    days = _days_correction(text)

    if days is not None:

        return {"corrections": {"days": days}}

    normalized = _norm(text)

    has_field_signal = (
        any(marker in normalized for marker in _FIELD_SIGNAL_MARKERS)
        or any(cue in normalized for cue in _CORRECTION_CUES)
        or bool(_METER_RE.search(normalized))
    )

    if has_field_signal:

        return None

    return _yn(text, "confirmed")


# ==========================================================
# ASK_MOVEMENT (como o iniciante se move hoje)
# ==========================================================


def _movement(text: str) -> dict | None:
    """Só resolve os casos triviais sem números; texto rico (tempos,
    velocidades) fica pro Gemini extrair capacidade completa."""

    normalized = _norm(text)

    # tem número (tempo/velocidade): deixa o Gemini extrair tudo
    if re.search(r"\d", normalized):

        return None

    has_walk = "caminh" in normalized

    has_run = any(
        marker in normalized
        for marker in ("trote", "trot", "corr", "corro")
    )

    if has_run and has_walk:

        return {"mobility": "run_walker"}

    if has_walk:

        return {"mobility": "walker"}

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
    "ASK_MOVEMENT": _movement,
    "ASK_COACH": lambda text: _yn(text, "has_coach"),
    "AWAIT_PLAN_MEDIA": _skip,
    "ASK_PACE": _pace,
    "ASK_DAYS": _days,
    "ASK_WEEK_CHOICE": _week_choice,
    "CONFIRM_DAYS": _confirm_days_only,
    "CONFIRM": _confirm_summary,
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
