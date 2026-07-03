from enum import Enum


class WorkoutType(str, Enum):

    RECOVERY = "RECOVERY"

    EASY = "EASY"

    TEMPO = "TEMPO"

    THRESHOLD = "THRESHOLD"

    VO2 = "VO2"

    INTERVAL = "INTERVAL"

    LONG_RUN = "LONG_RUN"

    RACE = "RACE"

    UNKNOWN = "UNKNOWN"