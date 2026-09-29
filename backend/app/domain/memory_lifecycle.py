"""Ciclo de vida da memória evolutiva — a HIGIENE que faltava (a memória só
nascia e ficava ativa pra sempre até a IA arquivar). Três mecanismos, puros e
testáveis:

1. EXPIRAÇÃO de fatos DATADOS/TEMPORÁRIOS: uma troca "referente à semana de
   10/08" morre depois daquela semana; "temporariamente/essa semana" dura pouco.
   CUIDADO: "a partir de DD/MM" / "desde" é INÍCIO (durável), NÃO janela — não
   expira por causa da data.
2. TTL por categoria pras VOLÁTEIS: `vida` (doença/evento passageiro) e `outro`
   (episódico) somem sozinhas se não reconfirmadas; preferência/objetivo/
   motivação/disponibilidade duráveis NÃO expiram por tempo.
3. DEDUP: fato novo quase-igual a um ativo (mesma categoria) supera o antigo.

Vive no DOMÍNIO (regra pura, sem IO) pra a infra poder aplicar a expiração
no active() sem violar camada. Ver [[project_preferencia_duravel_rotina]]."""

import re
import unicodedata
from datetime import date, timedelta

# TTL (dias) só das categorias VOLÁTEIS — as duráveis não estão aqui (None).
_CATEGORY_TTL_DAYS = {
    "vida": 14,     # doença/evento de vida passageiro
    "outro": 30,    # catch-all episódico
}

# INÍCIO (durável): a data marca DE QUANDO passa a valer, não até quando.
_START_HINTS = ("a partir de", "a partir do", "a partir da", "desde")

# LIMITADO (janela): o fato vale só por um período curto.
_BOUNDED_HINTS = (
    "na semana", "nesta semana", "essa semana", "esta semana",
    "referente a semana", "temporariamente", "por enquanto",
    "so essa", "so nesta", "amanha", "hoje", "proxima semana",
)

# dias de folga depois da data citada (cobre a semana + margem)
_DATE_GRACE_DAYS = 9

# janela curta quando é temporário SEM data explícita
_TEMPORARY_FALLBACK_DAYS = 10

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")

# AUSÊNCIA/PAUSA: fato que tem começo e FIM (o atleta volta). É o que o prazo
# explícito (`until`, escrito pela extração) cobre; estas pistas + duração ("por
# 7 dias", "até 05/10") são a REDE DE SEGURANÇA pro que a extração deixar escapar
# — a pausa médica do Renato (29/09) ficou eterna porque "por 7 dias" não era
# reconhecido como janela.
ABSENCE_CUES = (
    "ausent", "afast", "viaj", "viagem", "pausa", "pausar", "parar", "parad",
    "sem treinar", "sem correr", "repouso", "proibid", "nao pode",
    "nao vai poder", "nao podera", "impedid", "ferias", "licenca",
    "cirurgi", "procedimento", "internad", "recuper",
)

# só estas categorias entram na rede: lesão fica de fora (some quando o atleta
# disser que melhorou, não por relógio)
_ABSENCE_CATEGORIES = ("disponibilidade", "vida", "outro")

_NUM_WORDS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
    "onze": 11, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30,
}

_DURATION_RE = re.compile(
    r"(?<![\d/])(\d{1,3}|" + "|".join(_NUM_WORDS) + r")\s+"
    r"(dias?|semanas?|mes|meses)\b"
)

_UNTIL_DATE_RE = re.compile(r"\bate (?:o )?(?:dia )?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")

_WEEKDAYS = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "domingo": 6,
}

_UNTIL_WEEKDAY_RE = re.compile(r"\bate (?:a |o |proxima |proximo )?(" + "|".join(_WEEKDAYS) + r")")

# prazo explícito absurdo (erro de conta da IA) é ignorado
_MAX_UNTIL_DAYS = 400

# limiar de sobreposição (Jaccard de tokens) pra considerar quase-duplicata
_DEDUP_JACCARD = 0.6

# sinônimos do DOMÍNIO que significam a MESMA coisa — canonizados no token pra o
# dedup casar "enviar pro relógio" com "enviar pro Garmin" (mesmo aparelho).
# Mínimo e conservador de propósito (só termos inequívocos).
_SYNONYMS = {
    "relogio": "garmin",
    "watch": "garmin",
}

# stopwords curtas que não distinguem um fato do outro
_STOPWORDS = {
    "de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "no",
    "na", "nos", "nas", "um", "uma", "que", "com", "para", "pra", "por",
    "ao", "aos", "à", "se", "ele", "ela", "seu", "sua", "the",
}


class MemoryLifecycle:

    # ---------------------------------------------------------------- expiry

    @staticmethod
    def expiry_for(
        category: str,
        content: str,
        created_at: str,
        until: str | None = None,
    ) -> str | None:
        """Data de validade (ISO 'YYYY-MM-DD') do fato, ou None se durável.

        `until` = o ÚLTIMO dia em que o fato vale, escrito pela extração (a IA
        leu a mensagem e sabe a data de hoje) — manda sobre qualquer dedução.
        Sem ele, a dedução por texto: ausência com duração/data, depois janela
        curta e TTL por categoria."""

        created = MemoryLifecycle._to_date(created_at)

        explicit = MemoryLifecycle._explicit_until(until, created)

        if explicit is not None:

            return explicit.isoformat()

        text = MemoryLifecycle._normalize(content)

        # AUSÊNCIA com duração/data ("por 7 dias", "até 05/10"): tem FIM, mesmo
        # com "a partir de" (a duração conta do início citado)
        absence_end = MemoryLifecycle._absence_end(category, content, text, created)

        if absence_end is not None:

            return absence_end.isoformat()

        # INÍCIO ("a partir de X") -> durável: a data é começo, não fim
        if any(hint in text for hint in _START_HINTS):

            return MemoryLifecycle._category_expiry(category, created)

        # LIMITADO: janela curta. Se cita uma data, morre depois dela; senão,
        # janela curta a partir de quando o coach soube.
        if any(hint in text for hint in _BOUNDED_HINTS):

            cited = MemoryLifecycle._first_date(content, created.year)

            end = (
                cited + timedelta(days=_DATE_GRACE_DAYS)
                if cited is not None
                else created + timedelta(days=_TEMPORARY_FALLBACK_DAYS)
            )

            return end.isoformat()

        return MemoryLifecycle._category_expiry(category, created)

    @staticmethod
    def is_absence(category: str, content: str) -> bool:
        """O fato é uma AUSÊNCIA/PAUSA (viagem, afastamento, repouso)? — quem
        consulta o prazo (re-engajamento, contexto) só olha estas."""

        if category not in _ABSENCE_CATEGORIES and category != "lesao":

            return False

        text = MemoryLifecycle._normalize(content)

        return any(cue in text for cue in ABSENCE_CUES)

    @staticmethod
    def _explicit_until(until: str | None, created: date) -> date | None:

        if not until or not isinstance(until, str):

            return None

        try:

            end = date.fromisoformat(until[:10])

        except ValueError:

            return None

        if end < created or (end - created).days > _MAX_UNTIL_DAYS:

            return None

        return end

    @staticmethod
    def _absence_end(
        category: str, content: str, text: str, created: date,
    ) -> date | None:
        """Fim de uma ausência a partir do TEXTO: duração ("por 7 dias" -> conta
        do início, inclusive) ou "até DD/MM"/"até sexta". None sem pista de
        ausência ou sem prazo."""

        if category not in _ABSENCE_CATEGORIES:

            return None

        if not any(cue in text for cue in ABSENCE_CUES):

            return None

        until_date = _UNTIL_DATE_RE.search(text)

        if until_date:

            day, month, year = until_date.groups()

            try:

                yr = int(year) if year else created.year

                if yr < 100:

                    yr += 2000

                end = date(yr, int(month), int(day))

                if end < created and not year:

                    end = date(yr + 1, int(month), int(day))

                return end

            except ValueError:

                pass

        until_weekday = _UNTIL_WEEKDAY_RE.search(text)

        if until_weekday:

            target = _WEEKDAYS[until_weekday.group(1)]

            return created + timedelta(days=(target - created.weekday()) % 7)

        duration = _DURATION_RE.search(text)

        if not duration:

            return None

        amount = duration.group(1)

        n = int(amount) if amount.isdigit() else _NUM_WORDS[amount]

        unit = duration.group(2)

        days = n * (7 if unit.startswith("semana") else 30 if unit.startswith("mes") else 1)

        if days <= 0 or days > _MAX_UNTIL_DAYS:

            return None

        # "a partir de 29/09, por 7 dias": a conta é do início citado
        start = created

        if any(hint in text for hint in _START_HINTS):

            cited = MemoryLifecycle._first_date(content, created.year)

            if cited is not None:

                start = cited

        return start + timedelta(days=days - 1)

    @staticmethod
    def _category_expiry(category: str, created: date) -> str | None:

        ttl = _CATEGORY_TTL_DAYS.get(category)

        if ttl is None:

            return None

        return (created + timedelta(days=ttl)).isoformat()

    @staticmethod
    def is_expired(entry, on_date: date) -> bool:
        """O fato já venceu em `on_date`? Usa o expires_at gravado; se não houver
        (dado legado), DERIVA da categoria/conteúdo/data — assim a higiene vale
        retroativa sem migração."""

        expiry = getattr(entry, "expires_at", None) or MemoryLifecycle.expiry_for(
            entry.category, entry.content, entry.created_at,
        )

        if not expiry:

            return False

        parsed = MemoryLifecycle._to_date(expiry)

        return on_date > parsed

    # ------------------------------------------------------------------ dedup

    @staticmethod
    def is_near_duplicate(a: str, b: str) -> bool:
        """Dois fatos dizem essencialmente a mesma coisa? Sobreposição de tokens
        (Jaccard) OU contido um no outro. Conservador (mesma categoria, limiar
        alto) pra NÃO fundir fatos distintos — falso-merge é pior que duplicata.
        Limite conhecido: sinônimos (relógio/Garmin) escapam do léxico."""

        ta = MemoryLifecycle._tokens(a)
        tb = MemoryLifecycle._tokens(b)

        # sinal de menos de 3 tokens é fraco demais pra afirmar "é a mesma
        # coisa" — não funde (ex.: "Fato 0" vs "Fato 1")
        if min(len(ta), len(tb)) < 3:

            return False

        inter = len(ta & tb)

        union = len(ta | tb)

        jaccard = inter / union if union else 0.0

        # contido: o menor é subconjunto quase total do maior (≥3 tokens)
        smaller = min(len(ta), len(tb))

        contained = smaller >= 3 and inter >= smaller

        return jaccard >= _DEDUP_JACCARD or contained

    # ------------------------------------------------------------------ utils

    @staticmethod
    def _tokens(text: str) -> set[str]:

        norm = MemoryLifecycle._normalize(text)

        raw = re.findall(r"[a-z0-9]+", norm)

        return {
            _SYNONYMS.get(t, t)
            for t in raw
            if len(t) > 1 and t not in _STOPWORDS
        }

    @staticmethod
    def _normalize(text: str) -> str:
        """minúsculas + sem acento — pra casar 'à'/'a', 'terça'/'terca'."""

        nfkd = unicodedata.normalize("NFKD", text.lower())

        return "".join(c for c in nfkd if not unicodedata.combining(c))

    @staticmethod
    def _first_date(content: str, default_year: int) -> date | None:

        for match in _DATE_RE.finditer(content):

            day, month, year = match.groups()

            try:

                yr = int(year) if year else default_year

                if yr < 100:

                    yr += 2000

                return date(yr, int(month), int(day))

            except ValueError:

                continue

        return None

    @staticmethod
    def _to_date(iso: str) -> date:
        """Data de um ISO (date ou datetime). Fallback: hoje (nunca quebra)."""

        try:

            return date.fromisoformat(iso[:10])

        except (ValueError, TypeError):

            return date.today()
