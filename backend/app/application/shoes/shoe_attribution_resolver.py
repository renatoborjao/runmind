"""Decide QUAL tênis levou uma corrida — sem o atleta tagar treino a treino.
A cascata (a ordem importa): gear da fonte → escolha do atleta pra a data →
regra de rodízio → RECOMENDAÇÃO que o coach mostrou pra a data → tênis padrão.
Ver [[project_tracker_tenis]]."""

from dataclasses import dataclass

from app.domain.entities.shoe import Shoe, ShoeBook

# como a corrida foi atribuída — pra o coach explicar quando fizer sentido
BY_GEAR = "gear"
BY_ASSIGN = "assign"
BY_RULE = "rule"
BY_RECOMMENDED = "recommended"
BY_DEFAULT = "default"


@dataclass(slots=True)
class Attribution:

    shoe: Shoe

    how: str


class ShoeAttributionResolver:

    @staticmethod
    def resolve(
        book: ShoeBook,
        gear_id: str | None,
        labels: tuple[str, ...],
        session_date_iso: str | None = None,
    ) -> Attribution | None:
        """`labels` = tipo/rótulo do treino (plano + detectado) pra a regra de
        rodízio casar. `session_date_iso` = data da corrida (pra casar a escolha
        pontual do atleta e a recomendação que o coach mostrou pra aquele dia).
        None quando não há como atribuir (sem tênis ativos / nada que sirva)."""

        # 1) gear da fonte (Strava/Garmin): registro do que ele REALMENTE calçou
        by_gear = book.by_gear(gear_id)

        if by_gear is not None:

            return Attribution(by_gear, BY_GEAR)

        # 2) escolha PONTUAL do atleta pra ESTA data ("domingo vou de Red Hare")
        by_assign = ShoeAttributionResolver._active_pick(
            book, book.assignments.get(session_date_iso or "")
        )

        if by_assign is not None:

            return Attribution(by_assign, BY_ASSIGN)

        # 3) regra de rodízio que ele ensinou 1x ("tiros = Vaporfly")
        for rule in book.rules:

            if rule.matches(*labels):

                shoe = book.get(rule.shoe_id)

                if shoe is not None and not shoe.retired:

                    return Attribution(shoe, BY_RULE)

        # 4) a RECOMENDAÇÃO que o coach mostrou pra este dia: sem gear/regra, é o
        # melhor palpite do que ele calçou (ele costuma seguir a sugestão) — bem
        # melhor que jogar cego no padrão. A correção do atleta ainda sobrepõe.
        by_reco = ShoeAttributionResolver._active_pick(
            book, book.recommended.get(session_date_iso or "")
        )

        if by_reco is not None:

            return Attribution(by_reco, BY_RECOMMENDED)

        # 5) tênis do dia a dia (padrão)
        default = book.default()

        if default is not None:

            return Attribution(default, BY_DEFAULT)

        return None

    @staticmethod
    def _active_pick(book: ShoeBook, shoe_id: str | None) -> Shoe | None:
        """Resolve um shoe_id guardado (assignment/recomendação) pra um par
        ATIVO — ignora par aposentado ou id órfão."""

        if not shoe_id:

            return None

        shoe = book.get(shoe_id)

        return shoe if shoe is not None and not shoe.retired else None
