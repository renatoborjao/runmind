"""É o MESMO treino? — a regra única que colapsa a corrida que entra duas vezes
(Garmin + Strava, ids diferentes). Usada pelo arquivo de atividades e pelo
histórico de treino, pra as duas lerem a mesma verdade.

Dois sinais, o primeiro mais forte:

1. MESMO INSTANTE DE INÍCIO (±60 s) + distância ~igual (2%): a cópia do Strava
   nasce do relógio, então começa no mesmo segundo. O tempo em movimento NÃO
   entra: o Strava aplica pausa automática diferente do Garmin e os dois
   divergem 4–8% (Fernanda 16/10: Limiar 5,38 km — 1674 s no Garmin × 1807 s no
   Strava — contado 2×, e o resumo de domingo mostrou 35,8 km em vez de 30,4).
   Ninguém começa duas corridas no mesmo segundo.
2. Início DIFERENTE (offset de fuso, ~3 h, numa transição de fonte): mesma DATA
   + distância 0,5% + tempo em movimento 2% — apertado de propósito pra não
   fundir dois treinos reais do mesmo dia."""

from app.domain.entities.activity import Activity

SAME_START_SECONDS = 60

# a distância das duas cópias vem do mesmo GPS: difere em frações de metro
SAME_START_DISTANCE = 0.02

SAME_DAY_DISTANCE = 0.005

SAME_DAY_TIME = 0.02


def is_same_workout(a: Activity, b: Activity) -> bool:

    if a.id == b.id:

        return True

    biggest_dist = max(a.distance, b.distance, 1.0)

    if (
        a.distance > 0
        and b.distance > 0
        and _same_start(a, b)
        and abs(a.distance - b.distance) <= SAME_START_DISTANCE * biggest_dist
    ):

        return True

    if a.start_date.date() != b.start_date.date():

        return False

    if abs(a.distance - b.distance) > SAME_DAY_DISTANCE * biggest_dist:

        return False

    biggest_time = max(a.moving_time, b.moving_time, 1)

    return abs(a.moving_time - b.moving_time) <= SAME_DAY_TIME * biggest_time


def _same_start(a: Activity, b: Activity) -> bool:

    try:

        gap = abs((a.start_date - b.start_date).total_seconds())

    except TypeError:  # um com fuso, o outro sem: não dá pra comparar o instante

        return False

    return gap <= SAME_START_SECONDS
