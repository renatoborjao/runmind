from app.domain.entities.planned_session import PlannedSession

# Tiros de 400 m: o total dos tiros ocupa ~60% da sessão de qualidade,
# limitado a 4–8 repetições (o resto é aquecimento/desaquecimento).
VO2_REP_KM = 0.4
VO2_WORK_FRACTION = 0.6
VO2_MIN_REPS = 4
VO2_MAX_REPS = 8


class WorkoutGenerator:

    @staticmethod
    def generate_easy(distance: float):

        return PlannedSession(

            day="",

            workout_type="EASY",

            objective="Construção da base aeróbica",

            planned_distance_km=round(distance, 1),

            planned_duration_minutes=None,

            target_pace_min=None,

            target_pace_max=None,

            notes="",
        )

    @staticmethod
    def generate_progression(distance: float):
        """Rodagem que acelera no fim — estímulo de qualidade seguro
        para iniciantes (sem intervalados)."""

        return PlannedSession(

            day="",

            workout_type="PROGRESSION",

            objective="Estímulo de ritmo com segurança",

            planned_distance_km=round(distance, 1),

            planned_duration_minutes=None,

            target_pace_min=None,

            target_pace_max=None,

            notes="",
        )

    @staticmethod
    def generate_vo2(distance: float = 6.0):

        reps = WorkoutGenerator._vo2_reps(distance)

        return PlannedSession(

            day="",

            workout_type="VO2",

            objective="Potência aeróbica",

            planned_distance_km=round(distance, 1),

            planned_duration_minutes=None,

            target_pace_min=None,

            target_pace_max=None,

            notes=f"{reps}x400m",
        )

    @staticmethod
    def _vo2_reps(distance: float) -> int:

        raw = int(
            (distance * VO2_WORK_FRACTION) / VO2_REP_KM
        )

        return max(VO2_MIN_REPS, min(VO2_MAX_REPS, raw))

    @staticmethod
    def generate_long(distance: float):

        return PlannedSession(

            day="",

            workout_type="LONG_RUN",

            objective="Resistência",

            planned_distance_km=round(distance, 1),

            planned_duration_minutes=None,

            target_pace_min=None,

            target_pace_max=None,

            notes="",
        )

    @staticmethod
    def generate_tempo(distance: float):
        """Ritmo (tempo run): trecho contínuo em ritmo de limiar."""

        return PlannedSession(
            day="",
            workout_type="TEMPO",
            objective="Limiar anaeróbico",
            planned_distance_km=round(distance, 1),
            planned_duration_minutes=None,
            target_pace_min=None,
            target_pace_max=None,
            notes="",
        )

    @staticmethod
    def generate_fartlek(distance: float):
        """Fartlek: jogo de velocidades, variação livre de ritmo."""

        return PlannedSession(
            day="",
            workout_type="FARTLEK",
            objective="Ritmo de prova de forma lúdica",
            planned_distance_km=round(distance, 1),
            planned_duration_minutes=None,
            target_pace_min=None,
            target_pace_max=None,
            notes="",
        )

    @staticmethod
    def generate_recovery(distance: float):
        """Regenerativo: rodagem curta e bem leve pra recuperar."""

        return PlannedSession(
            day="",
            workout_type="RECOVERY",
            objective="Recuperação ativa",
            planned_distance_km=round(distance, 1),
            planned_duration_minutes=None,
            target_pace_min=None,
            target_pace_max=None,
            notes="",
        )

    @staticmethod
    def generate(workout_type: str, distance: float):
        """Despacha para o gerador do tipo (fallback: rodagem leve)."""

        builders = {
            "EASY": WorkoutGenerator.generate_easy,
            "RECOVERY": WorkoutGenerator.generate_recovery,
            "PROGRESSION": WorkoutGenerator.generate_progression,
            "TEMPO": WorkoutGenerator.generate_tempo,
            "VO2": WorkoutGenerator.generate_vo2,
            "FARTLEK": WorkoutGenerator.generate_fartlek,
            "LONG_RUN": WorkoutGenerator.generate_long,
        }

        builder = builders.get(
            workout_type,
            WorkoutGenerator.generate_easy,
        )

        return builder(distance)
