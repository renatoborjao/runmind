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
    ) -> str | None:
        """Data de validade (ISO 'YYYY-MM-DD') do fato, ou None se durável."""

        created = MemoryLifecycle._to_date(created_at)

        text = MemoryLifecycle._normalize(content)

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
