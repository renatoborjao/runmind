from app.domain.entities.planned_session import PlannedSession


class WorkoutGenerator:

    @staticmethod
    def generate_easy(distance: float):

        return PlannedSession(

            day="",

            workout_type="Easy Run",

            objective="Construção da base aeróbica",

            planned_distance_km=round(distance, 1),

            planned_duration_minutes=None,

            target_pace_min=None,

            target_pace_max=None,

            notes="Rodagem leve.",
        )

    @staticmethod
    def generate_vo2():

        return PlannedSession(

            day="",

            workout_type="VO2 Max",

            objective="Potência aeróbica",

            planned_distance_km=8,

            planned_duration_minutes=None,

            target_pace_min=None,

            target_pace_max=None,

            notes="6x800m",
        )

    @staticmethod
    def generate_long(distance: float):

        return PlannedSession(

            day="",

            workout_type="Long Run",

            objective="Resistência",

            planned_distance_km=round(distance, 1),

            planned_duration_minutes=None,

            target_pace_min=None,

            target_pace_max=None,

            notes="Longão.",
        )