from datetime import date

from app.application.history.weekly_buckets import activity_date
from app.domain.entities.daily_checkin import DailyCheckin
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.persistence.checkin_repository import CheckinRepository

# gripe/resfriado dura dias; depois disso o relato é velho (o atleta já seguiu)
WINDOW_DAYS = 10


class IllnessEpisode:
    """Doença relatada ainda EM ABERTO: o atleta disse que está doente (check-in
    com illness) nos últimos WINDOW_DAYS dias e NÃO correu desde o relato. É o
    que os proativos consultam pra não tratar um atleta doente como quem só
    furou (o Hélio resfriado recebeu o longão no bom dia e a cobrança do furo,
    26-27/09). Voltou a correr = episódio fechado."""

    @staticmethod
    def open(profile: str, activities, today: date) -> DailyCheckin | None:

        ill = CheckinRepository().recent_illness(
            profile, today.isoformat(), WINDOW_DAYS,
        )

        if ill is None:

            return None

        try:

            reported = date.fromisoformat(ill.day)

        except ValueError:

            return None

        ran_since = any(
            is_foot_sport(a.sport) and activity_date(a) > reported
            for a in activities or []
        )

        return None if ran_since else ill

    @staticmethod
    def reminder_line(ill: DailyCheckin) -> str:
        """Linha do lembrete do dia com a doença em aberto: orienta, o atleta
        decide (nunca cobra)."""

        try:

            when = f" ({date.fromisoformat(ill.day):%d/%m})"

        except ValueError:

            when = ""

        return (
            f"🤒 Você comentou que estava doente{when}. Se ainda não estiver "
            "100%, pula sem culpa — descansar agora é o treino. Se já passou, "
            "vai bem leve e me conta como o corpo respondeu."
        )

