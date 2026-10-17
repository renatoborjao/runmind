"""O CICLO de treino com várias provas: qual prova o ciclo SERVE e quanto cada
prova alivia a semana, pelo PAPEL dela (A principal · B preparatória · C de
treino). Alimenta os sinais DETERMINÍSTICOS que antes seguiam cegamente a prova
mais próxima: a fase de rede (`PhaseEngine`), o balanço de estímulos ("prova em
~N sem") e a zona de taper da descarga.

Só vale com CALENDÁRIO (`has_calendar`: 2+ provas à frente, ou 1 com papel B/C
escolhido). Sem calendário tudo devolve None/a âncora — comportamento idêntico ao
de antes. Quem decide o ciclo de verdade é a IA, lendo o calendário no dossiê
([[race_calendar_directive]]); aqui só os sinais de rede acompanham o papel.
Ver [[project_n_provas_design]] e [[feedback_ia_decide_sem_regras]]."""

from datetime import date

from app.application.coach.planning.race_calendar_directive import (
    future_races,
    has_calendar,
)
from app.domain.entities.training_goal import TrainingGoal

# semanas antes da prova em que o taper já alivia (não se empilha descarga de
# bloco em cima). Principal (ou papel indefinido) = o padrão da descarga, que
# NÃO está aqui (None); preparatória só tem um mini-polimento (1); de treino não
# alivia nada (-1: nenhuma semana até a prova cai na zona)
_TAPER_ZONE_WEEKS = {"B": 1, "C": -1}

_ROLE_WORD = {"B": "preparatória", "C": "de treino"}


def _role(race: dict) -> str | None:

    return race.get("priority_effective")


def focus_race(races: list[dict], today: date) -> dict | None:
    """A prova que o ciclo serve: a próxima PRINCIPAL; sem nenhuma principal
    definida, a mais próxima (papéis indefinidos = o comportamento antigo).
    None sem calendário."""

    if not has_calendar(races, today):

        return None

    ahead = future_races(races, today)

    principal = [r for r in ahead if _role(r) == "A"]

    return principal[0] if principal else ahead[0]


def focus_goal(
    races: list[dict], today: date, anchor: TrainingGoal
) -> TrainingGoal:
    """O TrainingGoal da prova-foco (distância, data e alvo DELA); a própria
    âncora quando não há calendário ou a foco já é a âncora."""

    focus = focus_race(races, today)

    if focus is None or focus.get("date") == (
        anchor.race_date.isoformat() if anchor.race_date else None
    ):

        return anchor

    return TrainingGoal(
        name=anchor.name,
        distance_km=focus.get("distance_km") or anchor.distance_km,
        target_time=focus.get("target_time"),
        race_date=date.fromisoformat(focus["date"]),
        priority="A",
    )


def taper_zone_weeks(races: list[dict], today: date) -> int | None:
    """Zona de taper da PRÓXIMA prova, pelo papel dela. None = padrão da
    descarga (sem calendário, prova principal ou papel indefinido)."""

    if not has_calendar(races, today):

        return None

    nearest = future_races(races, today)[0]

    return _TAPER_ZONE_WEEKS.get(_role(nearest))


def waypoint_note(races: list[dict], today: date) -> str:
    """Quando a próxima prova NÃO é a foco do ciclo (é preparatória ou de
    treino) e vem logo (<= 8 semanas): uma frase pro balanço de estímulos —
    o marco no caminho e como tratá-lo. Vazia sem calendário ou sem marco."""

    focus = focus_race(races, today)

    if focus is None:

        return ""

    nearest = future_races(races, today)[0]

    if nearest is focus or _role(nearest) not in _ROLE_WORD:

        return ""

    weeks = (date.fromisoformat(nearest["date"]) - today).days // 7

    if weeks > 8:

        return ""

    when = date.fromisoformat(nearest["date"]).strftime("%d/%m")

    km = nearest.get("distance_km")

    label = f"{km:g} km" if km else (nearest.get("name") or "prova")

    how = (
        "mini-polimento só na última semana, sem reorganizar o ciclo"
        if _role(nearest) == "B"
        else "entra como treino, sem polimento"
    )

    return (
        f"marco no caminho: {label} em {when} ({_ROLE_WORD[_role(nearest)]}, "
        f"em ~{weeks} sem) — {how}"
    )


class RaceCycle:
    """Leitura da lista de provas do atleta pros consumidores de rede."""

    @staticmethod
    def races(profile: str) -> list[dict]:
        """Provas do atleta (papel e distância já resolvidos). [] se falhar —
        sem lista, os sinais seguem o comportamento antigo."""

        try:

            from app.application.races.race_service import RaceService

            return RaceService.list(profile)

        except Exception as e:

            print(f"Ciclo de provas falhou p/ '{profile}': {e}")

            return []
