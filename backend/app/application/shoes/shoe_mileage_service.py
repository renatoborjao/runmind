"""Soma a km de cada corrida concluída no tênis certo — idempotente e à prova
de dupla-fonte (Garmin+Strava mandam a mesma corrida com ids diferentes). Roda
no evento de treino concluído. Quando o par cruza o limiar de desgaste, devolve
UM alerta pro coach mandar (dedup: um por par). Ver [[project_tracker_tenis]]."""

from dataclasses import dataclass

from app.application.shoes.shoe_attribution_resolver import (
    Attribution,
    ShoeAttributionResolver,
)
from app.domain.entities.shoe import Shoe
from app.infrastructure.persistence.shoe_repository import ShoeRepository


@dataclass(slots=True)
class ShoeMileageOutcome:

    shoe: Shoe

    km: float

    attribution: Attribution

    # texto do alerta de desgaste quando ESTA corrida cruzou o limiar; senão None
    wear_alert: str | None = None


class ShoeMileageService:

    @staticmethod
    def attribute(
        profile: str,
        runner_name: str,
        enriched,
        planned_session=None,
    ) -> ShoeMileageOutcome | None:
        """Atribui e soma a km desta corrida. None quando não há armário montado,
        não dá pra atribuir, ou a corrida já foi contada (idempotência/dedup)."""

        activity = getattr(enriched, "activity", None)

        if activity is None or not activity.distance:

            return None

        repo = ShoeRepository()

        book = repo.load(profile)

        # feature não configurada pra este atleta: silêncio total
        if not book.active():

            return None

        km = round(activity.distance / 1000, 2)

        day = activity.start_date.date().isoformat()

        # dedup cross-fonte: a mesma corrida vem por Strava E Garmin (ids
        # diferentes, +3h UTC) — mesma data + km ~igual. Guarda no armário.
        fingerprint = f"{day}:{round(km)}"

        if fingerprint in book.counted_fingerprints:

            return None

        gear_id = (activity.raw or {}).get("gear_id")

        labels = (
            getattr(planned_session, "workout_type", "") or "",
            getattr(enriched, "training_type", "") or "",
        )

        attribution = ShoeAttributionResolver.resolve(
            book, gear_id, labels, session_date_iso=day
        )

        if attribution is None:

            return None

        shoe = attribution.shoe

        # idempotência por id (reentrega do mesmo webhook)
        if activity.id in shoe.counted_ids:

            return None

        shoe.accumulated_km = round(shoe.accumulated_km + km, 2)

        shoe.counted_ids.append(activity.id)

        book.counted_fingerprints.append(fingerprint)

        # guarda a última atribuição pra a correção pontual ("hoje foi com o
        # de prova") poder mover a km pro par certo depois
        book.last_activity_id = activity.id

        book.last_shoe_id = shoe.id

        book.last_km = km

        wear_alert = None

        # cruzou o limiar AGORA (e ainda não avisamos): um alerta por par
        if not shoe.wear_alerted and shoe.total_km >= shoe.alert_threshold_km:

            shoe.wear_alerted = True

            wear_alert = ShoeMileageService._wear_message(runner_name, shoe)

        repo.save(profile, book)

        return ShoeMileageOutcome(
            shoe=shoe, km=km, attribution=attribution, wear_alert=wear_alert
        )

    @staticmethod
    def _wear_message(name: str, shoe: Shoe) -> str:
        """Aviso de desgaste na voz do coach: fato (km) + conduta (rodízio),
        sem alarmar. É o diferencial vs Strava — o coach AVISA, ele não precisa
        ir olhar."""

        return (
            f"Ei, {name}! Teu {shoe.label} acabou de passar dos "
            f"{round(shoe.total_km)} km. 👟 A partir dessa faixa a amortização "
            "começa a ceder e o risco de lesãozinha sobe — vale ir pensando em "
            "aposentar pra rodagem ou começar um rodízio com um par mais novo. "
            "Se quiser, eu te ajudo a organizar isso. 💪"
        )
