from enum import Enum


class DistanceStatus(str, Enum):

    ABOVE = "DISTANCE_ABOVE"

    BELOW = "DISTANCE_BELOW"

    OK = "DISTANCE_OK"

    UNKNOWN = "DISTANCE_UNKNOWN"


class TypeMatchStatus(str, Enum):

    MATCH = "TYPE_MATCH"

    MISMATCH = "TYPE_MISMATCH"


class IntensityLevel(str, Enum):

    VERY_HIGH = "INTENSITY_VERY_HIGH"

    HIGH = "INTENSITY_HIGH"

    MEDIUM = "INTENSITY_MEDIUM"

    LOW = "INTENSITY_LOW"


class RecoveryStatus(str, Enum):

    LONG = "RECOVERY_LONG"

    MODERATE = "RECOVERY_MODERATE"

    SHORT = "RECOVERY_SHORT"


class FatigueLevel(str, Enum):

    HIGH = "FATIGUE_HIGH"

    MODERATE = "FATIGUE_MODERATE"


class ConsistencyLevel(str, Enum):

    EXCELLENT = "CONSISTENCY_EXCELLENT"

    GOOD = "CONSISTENCY_GOOD"

    FAIR = "CONSISTENCY_FAIR"

    LOW = "CONSISTENCY_LOW"


class WeeklyVolumeStatus(str, Enum):

    COMPLETED = "WEEKLY_VOLUME_COMPLETED"

    NEAR_COMPLETE = "WEEKLY_VOLUME_NEAR"

    IN_PROGRESS = "WEEKLY_VOLUME_IN_PROGRESS"

    NO_GOAL = "WEEKLY_VOLUME_NO_GOAL"


class InjuryStatus(str, Enum):

    ACTIVE = "INJURY_ACTIVE"


class PaceEffortLevel(str, Enum):

    VERY_FAST = "PACE_VERY_FAST"

    FAST = "PACE_FAST"

    MODERATE = "PACE_MODERATE"

    EASY = "PACE_EASY"
