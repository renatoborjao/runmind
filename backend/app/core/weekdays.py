from datetime import datetime


WEEKDAYS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


WEEKDAYS_PTBR = {
    "monday": "segunda-feira",
    "tuesday": "terça-feira",
    "wednesday": "quarta-feira",
    "thursday": "quinta-feira",
    "friday": "sexta-feira",
    "saturday": "sábado",
    "sunday": "domingo",
}


def weekday_name(date: datetime) -> str:
    """
    Retorna o dia da semana no padrão utilizado
    internamente pelo RunMind.

    Independe do idioma do Windows.
    """

    return WEEKDAYS[date.weekday()]


def weekday_label(day: str) -> str:
    """Nome interno em inglês ("Thursday") -> exibição em pt-BR
    ("quinta-feira"). Dia desconhecido volta como veio."""

    return WEEKDAYS_PTBR.get(day.lower(), day)