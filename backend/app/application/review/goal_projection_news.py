"""O "rumo à meta" do resumo de domingo só aparece quando há NOVIDADE — ou uma vez
por mês. Falar toda semana a mesma projeção é repetir (nossa regra: o coach fala
por motivo novo; [[feedback_orientar_nao_mandar]]).

Novidade = a primeira vez, a meta/prova mudou, a projeção andou o bastante, ou a
prova entrou numa faixa mais próxima (12, 8, 4 semanas). Sem nenhuma: silêncio até
completar ~1 mês desde a última vez. Puro e determinístico (testável sem IA)."""

from datetime import date

# a projeção precisa andar isto (relativo) pra valer uma nova mensagem
MOVED_FRACTION = 0.01

# "1 vez por mês": passou isto desde a última vez mostrada, mostra de novo
MONTHLY_DAYS = 28


def weeks_band(weeks: int | None) -> str:
    """Faixa de proximidade da prova: muda quando ela se aproxima."""

    if weeks is None:

        return "none"

    if weeks > 12:

        return "far"

    if weeks > 8:

        return "12w"

    if weeks > 4:

        return "8w"

    if weeks > 0:

        return "4w"

    return "week"


def projection_is_news(
    last: dict | None, snapshot: dict, today: date
) -> tuple[bool, str]:
    """(mostra?, motivo). `last` = o que foi mostrado da última vez (com "date");
    `snapshot` = a projeção de hoje ({"seconds", "target_time", "distance_km",
    "race_date", "weeks"})."""

    if not last:

        return True, "first"

    try:

        days_since = (today - date.fromisoformat(last.get("date") or "")).days

    except ValueError:

        return True, "first"

    for key in ("distance_km", "target_time", "race_date"):

        if last.get(key) != snapshot.get(key):

            return True, "goal_changed"

    old = last.get("seconds")

    new = snapshot.get("seconds")

    if old and new and abs(new - old) / old >= MOVED_FRACTION:

        return True, "moved"

    if weeks_band(snapshot.get("weeks")) != weeks_band(last.get("weeks")):

        return True, "band"

    if days_since >= MONTHLY_DAYS:

        return True, "monthly"

    return False, "nothing_new"
