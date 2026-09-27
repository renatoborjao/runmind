from app.application.review.goal_projection_writer import GoalProjectionWriter
from app.domain.entities.training_goal import TrainingGoal


def _goal():
    return TrainingGoal(name="15k", distance_km=15.0, target_time="1:15:00", race_date=None)


def test_realistic_gap_says_reachable():
    # 1:16:30 previsto, alvo 1:15:00, 13 semanas → ~2% (0,15%/sem)
    line = GoalProjectionWriter._gap_line(
        _goal(), {"seconds": 4590, "delta_seconds": 90}, 13,
    )
    assert "realista" in line and "Sendo franco" not in line


def test_aggressive_gap_is_honest_with_realistic_target():
    """Caso real renato2: 1:23:18 previsto × 1:15:00 em 13 semanas ≈ 10% —
    acima de 0,8%/sem vira franqueza + alvo realista (antes: 'Dá pra chegar')."""
    line = GoalProjectionWriter._gap_line(
        _goal(), {"seconds": 4998, "delta_seconds": 498}, 10,
    )
    assert "Sendo franco" in line and "alvo realista" in line
    assert "Dá pra chegar" not in line


def test_without_weeks_keeps_neutral_encouragement():
    line = GoalProjectionWriter._gap_line(
        _goal(), {"seconds": 4998, "delta_seconds": 498}, None,
    )
    assert "consistência" in line
