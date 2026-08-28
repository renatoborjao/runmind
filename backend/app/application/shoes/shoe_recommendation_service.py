"""O coach DECIDE qual tênis usar em cada treino e AVISA na hora — antes da
corrida, não só conta a km depois. Determinístico (rápido/exato, sem IA por
mensagem), com sabedoria de treinador: regra ensinada → categoria×tipo de
treino → padrão, e desvia do par gasto. Ver [[project_tracker_tenis]]."""

from app.domain.entities.shoe import Shoe, ShoeBook
from app.infrastructure.persistence.shoe_repository import ShoeRepository

# treino de QUALIDADE/prova pede o par mais leve/rápido, se ele tiver um
_QUALITY_CUES = (
    "tiro", "veloc", "interval", "tempo", "limiar", "threshold", "fartlek",
    "vo2", "progress", "simulad", "prova", "race", "ritmo",
)

# categoria que marca o par de correr rápido (prova/competição/placa)
_RACE_CATEGORY_CUES = ("prova", "corrida", "race", "competi", "carbono", "leve")


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
        """(tênis, motivo curto) pro treino, ou None. A cascata: regra ensinada
        → qualidade casa com o par de prova → padrão. Desvia do par gasto pro
        alternativo mais novo, se houver."""

        active = book.active()

        if not active:

            return None

        labels = (
            getattr(session, "workout_type", "") or "",
            getattr(session, "training_type", "") or "",
        )

        base = ShoeRecommendationService._base_pick(book, active, labels)

        if base is None:

            return None

        shoe, reason = base

        # consciência de desgaste: se o par indicado já passou do limiar e há um
        # alternativo mais novo (ativo, abaixo do limiar), manda o novo
        if shoe.total_km >= shoe.alert_threshold_km:

            fresher = ShoeRecommendationService._freshest_under_threshold(
                active, exclude=shoe.id
            )

            if fresher is not None:

                return (
                    fresher,
                    f"teu {shoe.label} já tá em {round(shoe.total_km)} km — "
                    f"hoje vai de {fresher.label} pra poupar",
                )

        return shoe, reason

    @staticmethod
    def _base_pick(
        book: ShoeBook, active: list[Shoe], labels: tuple[str, ...]
    ) -> tuple[Shoe, str] | None:

        # 1) regra que ele ensinou ("tiros = Vaporfly")
        for rule in book.rules:

            if rule.matches(*labels):

                shoe = book.get(rule.shoe_id)

                if shoe is not None and not shoe.retired:

                    return shoe, f"é o teu par de {rule.match}"

        text = " ".join(labels).lower()

        # o LONGÃO é conforto/volume — vai SEMPRE no par do dia a dia, mesmo
        # progressivo (Renato: "longão é tênis dia a dia, nada de placa de
        # carbono"). Só tiro/tempo/prova (qualidade CURTA/rápida) puxam o leve.
        is_long = "long" in text

        is_quality = (not is_long) and any(cue in text for cue in _QUALITY_CUES)

        # 2) sem regra: treino de qualidade casa com o par de prova (se houver)
        if is_quality:

            racer = ShoeRecommendationService._race_shoe(active)

            if racer is not None:

                return racer, "treino forte, pede o par mais leve"

        # 3) padrão (dia a dia)
        default = book.default()

        if default is not None:

            if is_long:

                reason = "longão é conforto, teu par do dia a dia"

            elif not is_quality:

                reason = "rodagem tranquila, teu par do dia a dia"

            else:

                reason = ""

            return default, reason

        # sem padrão: se só tem um par ativo, é esse mesmo
        if len(active) == 1:

            return active[0], ""

        return None

    @staticmethod
    def _race_shoe(active: list[Shoe]) -> Shoe | None:

        for shoe in active:

            category = (shoe.category or "").lower()

            if any(cue in category for cue in _RACE_CATEGORY_CUES):

                return shoe

        return None

    @staticmethod
    def _freshest_under_threshold(
        active: list[Shoe], exclude: str
    ) -> Shoe | None:

        candidates = [
            s
            for s in active
            if s.id != exclude and s.total_km < s.alert_threshold_km
        ]

        if not candidates:

            return None

        return min(candidates, key=lambda s: s.total_km)
