"""Decide QUAL tênis levou uma corrida — sem o atleta tagar treino a treino.
A cascata (a ordem importa): gear da fonte → regra de rodízio → tênis padrão.
Ver [[project_tracker_tenis]]."""

from dataclasses import dataclass

from app.domain.entities.shoe import Shoe, ShoeBook

# como a corrida foi atribuída — pra o coach explicar quando fizer sentido
BY_GEAR = "gear"
BY_RULE = "rule"
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
    ) -> Attribution | None:
        """`labels` = tipo/rótulo do treino (plano + detectado) pra a regra de
        rodízio casar. None quando não há como atribuir (sem tênis ativos, ou
        sem gear/regra/padrão que sirva)."""

        # 1) gear da fonte (Strava/Garmin): o atleta já organiza lá -> manda
        by_gear = book.by_gear(gear_id)

        if by_gear is not None:

            return Attribution(by_gear, BY_GEAR)

        # 2) regra de rodízio que ele ensinou 1x ("tiros = Vaporfly")
        for rule in book.rules:

            if rule.matches(*labels):

                shoe = book.get(rule.shoe_id)

                if shoe is not None and not shoe.retired:

                    return Attribution(shoe, BY_RULE)

        # 3) tênis do dia a dia (padrão)
        default = book.default()

        if default is not None:

            return Attribution(default, BY_DEFAULT)

        return None
