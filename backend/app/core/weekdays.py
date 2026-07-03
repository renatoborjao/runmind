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


def weekday_name(date: datetime) -> str:
    """
    Retorna o dia da semana no padrão utilizado
    internamente pelo RunMind.

    Independe do idioma do Windows.
    """

    return WEEKDAYS[date.weekday()]