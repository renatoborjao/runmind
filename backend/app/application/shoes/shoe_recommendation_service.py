"""O coach DECIDE qual tênis usar em cada treino e AVISA na hora — antes da
corrida, não só conta a km depois. Determinístico (rápido/exato, sem IA por
mensagem), com sabedoria de treinador:

- casa o TIPO de treino com a FUNÇÃO do par (qualidade → par de prova; rodagem/
  longão → dia a dia), respeitando regra que o atleta ensinou;
- REVEZA entre os pares da mesma função (é pra isso que se tem vários!) —
  espalha o desgaste, variando por dia e favorecendo o mais NOVO;
- desvia do par gasto pro mais novo.

Ver [[project_tracker_tenis]]."""

from app.domain.entities.shoe import Shoe, ShoeBook
from app.infrastructure.persistence.shoe_repository import ShoeRepository

# treino de QUALIDADE/prova pede o par mais leve/rápido, se ele tiver um
_QUALITY_CUES = (
    "tiro", "veloc", "interval", "tempo", "limiar", "threshold", "fartlek",
    "vo2", "progress", "simulad", "prova", "race", "ritmo",
)

# categoria que marca o par de correr rápido (prova/competição/placa)
_RACE_CATEGORY_CUES = ("prova", "corrida", "race", "competi", "carbono", "leve")

_WEEKDAY = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


class ShoeRecommendationService:

    @staticmethod
    def line(profile: str, session) -> str:
        """Linha de sugestão pra anexar na mensagem do treino. Vazia quando o
        atleta não montou o armário (silêncio total) ou não dá pra sugerir."""

        book = ShoeRepository().load(profile)

        pick = ShoeRecommendationService.recommend(book, session)

        if pick is None:

            return ""

        shoe, reason = pick

        tail = f" — {reason}" if reason else ""

        return f"👟 Sugestão de tênis: {shoe.label}{tail}"

    @staticmethod
    def recommend(book: ShoeBook, session) -> tuple[Shoe, str] | None:
        """(tênis, motivo curto) pro treino, ou None."""

        active = book.active()

        if not active:

            return None

        labels = (
            getattr(session, "workout_type", "") or "",
            getattr(session, "training_type", "") or "",
        )

        # 1) regra que o atleta ensinou ("tiros = Vaporfly") — override explícito
        for rule in book.rules:

            if rule.matches(*labels):

                shoe = book.get(rule.shoe_id)

                if shoe is not None and not shoe.retired:

                    return ShoeRecommendationService._with_wear_guard(
                        shoe, active, session, f"é o teu par de {rule.match}"
                    )

        text = " ".join(labels).lower()

        # o LONGÃO é conforto/volume — vai no dia a dia mesmo progressivo (Renato:
        # "longão é dia a dia, nada de placa"). Só qualidade CURTA/rápida puxa leve.
        is_long = "long" in text

        is_quality = (not is_long) and any(c in text for c in _QUALITY_CUES)

        prova = [s for s in active if ShoeRecommendationService._is_race(s)]

        daily = [s for s in active if not ShoeRecommendationService._is_race(s)]

        # 2) qualidade -> reveza entre os pares de PROVA (se houver)
        if is_quality and prova:

            return ShoeRecommendationService._from_bucket(
                prova, session, ShoeRecommendationService._quality_reason(prova),
            )

        # 3) rodagem/longão -> reveza entre os pares do DIA A DIA
        if daily:

            reason = ShoeRecommendationService._daily_reason(daily, is_long)

            return ShoeRecommendationService._from_bucket(daily, session, reason)

        # 4) sem balde do dia a dia: cai no que houver (padrão/prova/único)
        fallback = book.default() or (active[0] if len(active) == 1 else None)

        if fallback is not None:

            return ShoeRecommendationService._with_wear_guard(
                fallback, active, session, "",
            )

        # só tem pares de prova e o treino é fácil: reveza entre eles mesmo
        if prova:

            return ShoeRecommendationService._from_bucket(prova, session, "")

        return None

    # ---- rodízio ---------------------------------------------------------

    @staticmethod
    def _from_bucket(
        bucket: list[Shoe], session, reason: str
    ) -> tuple[Shoe, str]:
        """Escolhe um par do balde REVEZANDO: ordena do mais novo pro mais
        rodado e gira pelo dia da semana — dias diferentes pegam pares
        diferentes, e o mais novo é favorecido. Depois aplica o desvio de
        desgaste dentro do balde."""

        ordered = sorted(bucket, key=lambda s: s.total_km)

        idx = ShoeRecommendationService._day_index(session) % len(ordered)

        pick = ordered[idx]

        return ShoeRecommendationService._wear_swap(pick, bucket, reason)

    @staticmethod
    def _with_wear_guard(
        shoe: Shoe, active: list[Shoe], session, reason: str
    ) -> tuple[Shoe, str]:
        """Par escolhido por regra/fallback: se estiver gasto, troca pelo mais
        novo do MESMO balde (não põe racer em rodagem)."""

        same_bucket = [
            s for s in active
            if ShoeRecommendationService._is_race(s)
            == ShoeRecommendationService._is_race(shoe)
        ]

        return ShoeRecommendationService._wear_swap(shoe, same_bucket, reason)

    @staticmethod
    def _wear_swap(
        pick: Shoe, bucket: list[Shoe], reason: str
    ) -> tuple[Shoe, str]:
        """Se o par escolhido passou da vida útil e há um mais novo (abaixo do
        limiar) no balde, manda o novo — explicando o porquê."""

        if pick.total_km < pick.alert_threshold_km:

            return pick, reason

        fresher = [
            s for s in bucket
            if s.id != pick.id and s.total_km < s.alert_threshold_km
        ]

        if not fresher:

            return pick, reason

        novo = min(fresher, key=lambda s: s.total_km)

        return (
            novo,
            f"teu {pick.label} já tá em {round(pick.total_km)} km — hoje vai "
            f"de {novo.label} pra poupar",
        )

    # ---- rótulos ---------------------------------------------------------

    @staticmethod
    def _quality_reason(prova: list[Shoe]) -> str:

        if len(prova) > 1:

            return "treino forte — revezando teus pares leves"

        return "treino forte, teu par mais leve"

    @staticmethod
    def _daily_reason(daily: list[Shoe], is_long: bool) -> str:

        rev = " — revezando teus pares do dia a dia" if len(daily) > 1 else \
            ", teu par do dia a dia"

        base = "longão é conforto" if is_long else "rodagem tranquila"

        return base + rev

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _is_race(shoe: Shoe) -> bool:

        category = (shoe.category or "").lower()

        return any(cue in category for cue in _RACE_CATEGORY_CUES)

    @staticmethod
    def _day_index(session) -> int:

        return _WEEKDAY.get((getattr(session, "day", "") or "").lower(), 0)
