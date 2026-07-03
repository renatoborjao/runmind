from app.domain.entities.training_goal import TrainingGoal


class PhaseEngine:
    """
    Responsável por descobrir
    em qual fase do ciclo o atleta está.
    """

    @staticmethod
    def execute(goal: TrainingGoal) -> str:

        # Por enquanto retornaremos BUILD.
        # Depois calcularemos baseado na data da prova.

        return "BUILD"