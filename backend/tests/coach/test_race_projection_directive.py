from app.application.coach.planning.race_projection_directive import (
    race_projection_directive,
)
from app.domain.entities.race_prediction import RacePrediction
from app.domain.entities.training_goal import TrainingGoal

# projeção real do renato2 (10K 51:26)
_PRED = RacePrediction(
    time_5k_sec=1453, time_10k_sec=3086,
    time_half_sec=7064, time_marathon_sec=15569,
)


def _goal(distance_km=10.0, target_time="50:00"):

    return TrainingGoal(
        name="correr 10k", distance_km=distance_km,
        target_time=target_time, race_date=None,
    )


def test_meta_perto_orienta_qualidade_especifica():
    # 10K projetado 51:26 vs meta 50:00 → falta ~1min26 → PERTO
    out = race_projection_directive(_PRED, _goal())

    assert "51:26" in out
    assert "PERTO" in out
    assert "1min26" in out
    # é insumo, não decreto (disclaimer sempre presente)
    assert "ESTIMATIVA" in out and "não decreto" in out
    assert "GRADUAL" in out


def test_projecao_ja_bate_a_meta():
    # meta 52:00, projeção 51:26 → já alcança (folga)
    out = race_projection_directive(_PRED, _goal(target_time="52:00"))

    assert "JÁ alcança" in out


def test_meta_ainda_longe_pede_paciencia():
    # meta agressiva 45:00, projeção 51:26 → ~6min à frente → periodizar
    out = race_projection_directive(_PRED, _goal(target_time="45:00"))

    assert "periodize com paciência" in out
    assert "não force" in out


def test_sem_tempo_meta_ancora_capacidade():
    out = race_projection_directive(_PRED, _goal(target_time=None))

    assert "âncora de capacidade" in out or "capacidade" in out
    assert "51:26" in out


def test_sem_projecao_vazio():
    assert race_projection_directive(None, _goal()) == ""
    assert race_projection_directive(RacePrediction(), _goal()) == ""


def test_meta_distancia_nao_padrao_da_retrato_geral():
    # meta de 15 km (não casa 5/10/21/42) → lista as projeções como capacidade
    out = race_projection_directive(_PRED, _goal(distance_km=15.0, target_time=None))

    assert "capacidade projetada" in out
    assert "10K ~51:26" in out


def test_parse_meia_maratona_com_horas():
    # meta meia em 1:55:00, projeção 1:57:44 → falta ~2min44 (usa H:MM:SS)
    goal = TrainingGoal(
        name="meia", distance_km=21.0975, target_time="1:55:00", race_date=None,
    )

    out = race_projection_directive(_PRED, goal)

    assert "1:57:44" in out
    assert "2min44" in out
