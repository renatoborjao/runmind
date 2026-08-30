"""O coach DECIDE qual tênis usar em cada treino e AVISA na hora. Determinístico
(rápido/exato, sem IA por mensagem), com sabedoria de treinador:

- 3 FUNÇÕES: `rápido` (racer/placa — tiro/tempo/prova), `versátil` (super
  trainer — encaixa em TUDO), `dia a dia` (trainer amortecido — rodagem/longão);
- casa o TIPO de treino com a função: qualidade → rápido > versátil > dia a dia;
  rodagem/longão → dia a dia + versátil (juntos), senão rápido;
- REVEZA entre os pares elegíveis (é pra isso que se tem vários!) — favorece o
  mais NOVO e varia por dia; desvia do par gasto;
- a escolha PONTUAL do atleta (assign) e a regra durável dele mandam. O coach
  OPINA, o atleta DECIDE. Ver [[project_tracker_tenis]]."""

from app.domain.entities.shoe import Shoe, ShoeBook
from app.infrastructure.persistence.shoe_repository import ShoeRepository

# treino de QUALIDADE (tiro/tempo/fartlek/...) — pede o par de prova/versátil
_QUALITY_CUES = (
    "tiro", "veloc", "interval", "tempo", "limiar", "threshold", "fartlek",
    "vo2", "progress", "simulad", "prova", "race", "ritmo",
)

# categoria -> função (3 níveis). A ordem checa RÁPIDO (racer/placa) antes de
# VERSÁTIL (super trainer), pra placa não cair como versátil. "rápido" é o rótulo
# atual; "prova" segue aceito (dado antigo) — os dois caem no balde veloz.
_PROVA_CUES = (
    "rápido", "rapido", "veloz", "prova", "race", "raci", "carbon", "placa",
    "competi", "racer",
)
_VERSATIL_CUES = (
    "versát", "versat", "super trainer", "supertrainer", "speed", "leve",
)

_WEEKDAY = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_PROVA, _VERSATIL, _DAILY = "prova", "versatil", "diaadia"


class ShoeRecommendationService:

    @staticmethod
    def line(profile: str, session, session_date=None, week_sessions=None) -> str:
        """Linha de sugestão pra anexar na mensagem do treino. Vazia quando o
        atleta não montou o armário (silêncio total) ou não dá pra sugerir."""

        book = ShoeRepository().load(profile)

        pick = ShoeRecommendationService.recommend(
            book, session, session_date, week_sessions
        )

        if pick is None:

            return ""

        shoe, reason = pick

        tail = f" — {reason}" if reason else ""

        return f"👟 Sugestão de tênis: {shoe.label}{tail}"

    @staticmethod
    def recommend(
        book: ShoeBook, session, session_date=None, week_sessions=None
    ) -> tuple[Shoe, str] | None:
        """(tênis, motivo curto) pro treino, ou None. `week_sessions` (os treinos
        da semana em ordem) faz o rodízio girar pela POSIÇÃO do treino, não pelo
        dia da semana — espalha de verdade pela frota."""

        active = book.active()

        if not active:

            return None

        # escolha PONTUAL do atleta pra ESTA data ("quero o Red Hare no domingo")
        chosen = ShoeRecommendationService._assigned(book, session_date)

        if chosen is not None:

            return chosen, "você pediu esse pra hoje 👍"

        labels = (
            getattr(session, "workout_type", "") or "",
            getattr(session, "training_type", "") or "",
        )

        # regra durável do atleta ("SEMPRE tiro = Vaporfly") — override explícito
        for rule in book.rules:

            if rule.matches(*labels):

                shoe = book.get(rule.shoe_id)

                if shoe is not None and not shoe.retired:

                    return ShoeRecommendationService._with_wear_guard(
                        shoe, active, f"é o teu par de {rule.match}"
                    )

        text = " ".join(labels).lower()

        # longão é conforto/volume -> dia a dia (Renato). Só qualidade CURTA puxa
        # o leve. Progressivo conta como longão (não é qualidade curta).
        is_long = "long" in text

        is_quality = (not is_long) and any(c in text for c in _QUALITY_CUES)

        pool, reason = ShoeRecommendationService._pool(active, is_quality, is_long)

        if not pool:

            return None

        index = ShoeRecommendationService._rotation_index(
            session, is_quality, week_sessions
        )

        return ShoeRecommendationService._from_pool(pool, index, reason)

    @staticmethod
    def _rotation_index(session, is_quality: bool, week_sessions) -> int:
        """Posição do treino entre os da MESMA intenção (qualidade × fácil) na
        semana — o 1º treino fácil pega o 1º par, o 2º pega o 2º, etc. Sem os
        treinos da semana, cai no dia da semana (melhor que nada)."""

        if not week_sessions:

            return ShoeRecommendationService._day_index(session)

        index = 0

        for other in week_sessions:

            if ShoeRecommendationService._same_session(other, session):

                return index

            if ShoeRecommendationService._is_quality(other) == is_quality:

                index += 1

        return index

    @staticmethod
    def _is_quality(session) -> bool:

        text = " ".join(
            (
                getattr(session, "workout_type", "") or "",
                getattr(session, "training_type", "") or "",
            )
        ).lower()

        return ("long" not in text) and any(c in text for c in _QUALITY_CUES)

    @staticmethod
    def _same_session(a, b) -> bool:

        return a is b or (
            getattr(a, "day", None) == getattr(b, "day", None)
            and getattr(a, "workout_type", None) == getattr(b, "workout_type", None)
        )

    # ---- escolha do balde -------------------------------------------------

    @staticmethod
    def _pool(
        active: list[Shoe], is_quality: bool, is_long: bool
    ) -> tuple[list[Shoe], str]:
        """O conjunto elegível + o motivo. Qualidade: prova > versátil > dia a
        dia. Rodagem/longão: dia a dia + versátil (juntos) > prova."""

        prova = [s for s in active if ShoeRecommendationService._tier(s) == _PROVA]
        versatil = [
            s for s in active if ShoeRecommendationService._tier(s) == _VERSATIL
        ]
        daily = [s for s in active if ShoeRecommendationService._tier(s) == _DAILY]

        if is_quality:

            if prova:

                return prova, ShoeRecommendationService._rev(
                    "treino forte, teu par rápido", prova
                )

            if versatil:

                return versatil, ShoeRecommendationService._rev(
                    "treino forte, teu super trainer dá conta", versatil
                )

            if daily:

                return daily, "treino forte — sem par mais leve, vai no dia a dia"

            return active, ""

        # rodagem / longão: prioriza o DIA A DIA puro (reserva o versátil pra
        # qualidade / pros dias que o atleta fixar). Versátil e prova só entram
        # se não houver trainer de conforto.
        base = "longão é conforto" if is_long else "rodagem tranquila"

        if daily:

            return daily, ShoeRecommendationService._rev(
                f"{base}, teu par do dia a dia", daily
            )

        if versatil:

            return versatil, base

        if prova:

            return prova, base

        return active, ""

    @staticmethod
    def _rev(reason: str, pool: list[Shoe]) -> str:
        """Troca o final por '— revezando ...' quando há mais de um par no balde."""

        if len(pool) <= 1:

            return reason

        head = reason.rsplit(",", 1)[0]

        return f"{head} — revezando teus pares"

    # ---- rodízio ---------------------------------------------------------

    @staticmethod
    def _from_pool(
        pool: list[Shoe], index: int, reason: str
    ) -> tuple[Shoe, str]:
        """Escolhe REVEZANDO: ordena do mais novo pro mais rodado e gira pela
        POSIÇÃO do treino na semana — o 1º treino pega o mais novo, o 2º o
        próximo, etc. (espalha pela frota). Depois aplica o desvio de desgaste."""

        ordered = sorted(pool, key=lambda s: s.total_km)

        return ShoeRecommendationService._wear_swap(
            ordered[index % len(ordered)], pool, reason
        )

    @staticmethod
    def _with_wear_guard(
        shoe: Shoe, active: list[Shoe], reason: str
    ) -> tuple[Shoe, str]:
        """Par escolhido por regra: se gasto, troca pelo mais novo de MESMA
        função (não muda o tipo de par)."""

        tier = ShoeRecommendationService._tier(shoe)

        same = [s for s in active if ShoeRecommendationService._tier(s) == tier]

        return ShoeRecommendationService._wear_swap(shoe, same, reason)

    @staticmethod
    def _wear_swap(
        pick: Shoe, pool: list[Shoe], reason: str
    ) -> tuple[Shoe, str]:
        """Se o par escolhido passou da vida útil e há um mais novo (abaixo do
        limiar) no balde, manda o novo — explicando o porquê."""

        if pick.total_km < pick.alert_threshold_km:

            return pick, reason

        fresher = [
            s for s in pool
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

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _tier(shoe: Shoe) -> str:
        """Função do par pelos 3 níveis. PROVA antes de VERSÁTIL (placa não é
        versátil). Sem categoria -> dia a dia (neutro)."""

        category = (shoe.category or "").lower()

        if any(cue in category for cue in _PROVA_CUES):

            return _PROVA

        if any(cue in category for cue in _VERSATIL_CUES):

            return _VERSATIL

        return _DAILY

    @staticmethod
    def _assigned(book: ShoeBook, session_date) -> Shoe | None:
        """O par que o atleta fixou pra ESTA data, se ativo. None senão."""

        if session_date is None or not book.assignments:

            return None

        shoe_id = book.assignments.get(str(session_date))

        if shoe_id is None:

            return None

        shoe = book.get(shoe_id)

        return shoe if (shoe is not None and not shoe.retired) else None

    @staticmethod
    def _day_index(session) -> int:

        return _WEEKDAY.get((getattr(session, "day", "") or "").lower(), 0)
