"""O tênis do atleta e o 'armário' dele — o modelo de dados do contador de km
por par. Km é NÚMERO (soma determinística), por isso vive aqui/num repositório
dedicado, não como texto na memória evolutiva. Ver [[project_tracker_tenis]]."""

from __future__ import annotations

from dataclasses import dataclass, field

# limiar de desgaste padrão (km) — a partir daqui o coach sugere o rodízio.
# Tênis comum aguenta ~600-800km; placa de carbono bem menos. É só o default;
# cada tênis pode ter o seu (o atleta diz "esse aguenta menos").
DEFAULT_WEAR_KM = 700.0


def heal_mojibake(text: str | None) -> str | None:
    """Cura texto UTF-8 que foi salvo lido-como-Latin1 ('versÃ¡til' -> 'versátil',
    'rÃ¡pido' -> 'rápido'). Texto já correto (ou puro ASCII) passa intacto —
    o round-trip falha e a gente devolve o original. None-safe."""

    if not text:

        return text

    try:

        return text.encode("latin-1").decode("utf-8")

    except (UnicodeEncodeError, UnicodeDecodeError):

        return text


# os 3 rótulos de função canônicos + os sinônimos que a IA/atleta/dado antigo
# usam. "prova" é sinônimo histórico de "rápido". Fonte ÚNICA de verdade — o
# engine (recategorize), a listagem e o grounding do chat passam por aqui.
_CATEGORY_SYNONYMS = {
    "rápido": ("rápido", "rapido", "prova", "racer", "race", "veloz"),
    "versátil": (
        "versátil", "versatil", "super trainer", "supertrainer",
        "super-trainer",
    ),
    "dia a dia": ("dia a dia", "diaadia", "daily"),
}


def canonical_category(value: str | None) -> str | None:
    """Normaliza o rótulo de função pros 3 valores canônicos ('rápido',
    'versátil', 'dia a dia'), curando mojibake antes. None se não reconhece."""

    text = (heal_mojibake(value) or "").strip().lower()

    if not text:

        return None

    for canon, synonyms in _CATEGORY_SYNONYMS.items():

        if text in synonyms:

            return canon

    return None


@dataclass(slots=True)
class Shoe:

    id: str

    name: str

    nickname: str | None = None

    # categoria livre ("dia a dia", "prova", "treino") — ajuda a regra de
    # rodízio e a fala do coach; nunca é obrigatória
    category: str | None = None

    # id do equipamento no Strava (o `gear_id` da atividade) — quando casado,
    # é a fonte AUTORITATIVA de atribuição (o atleta já organiza lá)
    gear_id: str | None = None

    # o tênis do dia a dia: recebe as corridas sem gear nem regra
    is_default: bool = False

    # aposentado: não recebe mais km nem entra no rodízio (guardado pro histórico)
    retired: bool = False

    # km que o par JÁ tinha quando entrou no Ritmind (a vida real do solado não
    # começa do zero) + km acumulado por nós. total = os dois.
    initial_km: float = 0.0

    accumulated_km: float = 0.0

    alert_threshold_km: float = DEFAULT_WEAR_KM

    # o alerta de desgaste já saiu pra este par (dedup: um por episódio de
    # desgaste). Rearma se o atleta subir o limiar ou trocar o solado.
    wear_alerted: bool = False

    # ids das atividades já contadas NESTE par (idempotência do acumulador)
    counted_ids: list[int] = field(default_factory=list)

    created_at: str = ""

    @property
    def total_km(self) -> float:
        """A vida REAL do solado: o que já rodou antes + o que rodou conosco."""

        return round(self.initial_km + self.accumulated_km, 1)

    @property
    def label(self) -> str:

        return self.nickname or self.name


@dataclass(slots=True)
class ShoeRule:
    """Regra de rodízio que o atleta ensina uma vez ('tiros e provas =
    Vaporfly'): casa por PALAVRA no tipo/rótulo do treino e atribui ao par.
    O atleta não taga treino a treino — o coach aplica isto sozinho."""

    match: str          # palavra-chave no tipo/rótulo do treino (ex.: "tiro")

    shoe_id: str

    def matches(self, *labels: str) -> bool:

        needle = self.match.strip().lower()

        return bool(needle) and any(
            needle in (label or "").lower() for label in labels
        )


@dataclass(slots=True)
class ShoeBook:
    """O armário do atleta: os tênis + as regras de rodízio + a marca das
    corridas já contadas (dedup cross-fonte Garmin↔Strava — a mesma corrida vem
    das duas com ids diferentes)."""

    shoes: list[Shoe] = field(default_factory=list)

    rules: list[ShoeRule] = field(default_factory=list)

    # fingerprints "YYYY-MM-DD:km" das corridas já somadas — guarda contra
    # contar 2x a mesma corrida quando ela chega por Strava E por Garmin
    counted_fingerprints: list[str] = field(default_factory=list)

    # escolhas PONTUAIS do atleta: {data ISO do treino -> shoe_id}. "quero o
    # Red Hare no domingo" sobrepõe a recomendação SÓ naquele dia (não é regra
    # durável — vale pra aquela data). Ver [[ShoeRecommendationService]].
    assignments: dict[str, str] = field(default_factory=dict)

    # o que o COACH recomendou e MOSTROU pra cada data: {data ISO -> shoe_id}.
    # Sem gear do Strava nem regra, é o melhor palpite do que o atleta calçou
    # (ele costuma seguir a sugestão) — a atribuição conta NELE, não no padrão
    # cego. Gravado quando a sugestão é exibida; a correção do atleta ainda
    # manda. Ver [[ShoeRecommendationService]] e [[ShoeAttributionResolver]].
    recommended: dict[str, str] = field(default_factory=dict)

    # a ÚLTIMA corrida atribuída — pra a correção pontual ("hoje foi com o de
    # prova") mover a km do par errado pro certo, sem o atleta refazer nada
    last_activity_id: int | None = None

    last_shoe_id: str | None = None

    last_km: float = 0.0

    def active(self) -> list[Shoe]:

        return [s for s in self.shoes if not s.retired]

    def get(self, shoe_id: str) -> Shoe | None:

        return next((s for s in self.shoes if s.id == shoe_id), None)

    def default(self) -> Shoe | None:

        return next((s for s in self.active() if s.is_default), None)

    def by_gear(self, gear_id: str | None) -> Shoe | None:

        if not gear_id:

            return None

        return next(
            (s for s in self.active() if s.gear_id == gear_id), None
        )
