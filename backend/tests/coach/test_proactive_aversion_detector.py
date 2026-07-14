import pytest

from app.application.coach.intelligence import (
    proactive_aversion_detector as detector_module,
)
from app.application.coach.intelligence.proactive_aversion_detector import (
    ProactiveAversionDetector,
)
from app.infrastructure.persistence import (
    stimulus_miss_repository as repo_module,
)
from tests.coach.factories import (
    make_enriched_activity,
    make_planned_session,
    make_runner,
)


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    """Isola o histórico de 'evitou' num diretório temporário por teste."""

    monkeypatch.setattr(repo_module, "_STORAGE", tmp_path / "stimulus_miss")


_SPEED_PLANNED = {"workout_type": "VO2"}

_AVOIDED = {"training_type": "RODAGEM"}   # rebaixou o tiro

_DONE = {"training_type": "VO2"}          # fez o tiro


def _feed(runner, planned_overrides, executed_overrides):

    return ProactiveAversionDetector.after_feedback(
        runner,
        make_planned_session(**planned_overrides),
        make_enriched_activity(**executed_overrides),
    )


def test_opens_conversation_after_three_of_last_four():
    """Precisa da janela cheia (4 treinos da família); só então 3 evitados
    disparam a conversa — nunca antes."""

    runner = make_runner()

    # três primeiros: janela ainda não fechou -> silêncio
    for _ in range(3):

        assert _feed(runner, _SPEED_PLANNED, _AVOIDED) is None

    # quarto evitado fecha a janela (4/4) -> abre a conversa
    message = _feed(runner, _SPEED_PLANNED, _AVOIDED)

    assert message is not None
    assert "velocidade" in message


def test_good_session_in_window_still_triggers_at_three():
    """Um bom treino no meio não impede: 3 evitados nos últimos 4 basta."""

    runner = make_runner()

    _feed(runner, _SPEED_PLANNED, _AVOIDED)
    _feed(runner, _SPEED_PLANNED, _AVOIDED)
    _feed(runner, _SPEED_PLANNED, _DONE)     # bom treino no meio

    message = _feed(runner, _SPEED_PLANNED, _AVOIDED)  # [T,T,F,T] = 3/4

    assert message is not None


def test_does_not_repeat_until_pattern_breaks():
    """Depois de abrir a conversa, não repete a cada treino evitado; só volta
    a valer depois de um bom treino (que rearma o gatilho)."""

    runner = make_runner()

    for _ in range(4):

        _feed(runner, _SPEED_PLANNED, _AVOIDED)  # o 4º já abriu a conversa

    # mais um evitado: continua padrão, mas já avisamos -> silêncio
    assert _feed(runner, _SPEED_PLANNED, _AVOIDED) is None

    # bom treino rearma o gatilho
    assert _feed(runner, _SPEED_PLANNED, _DONE) is None

    # volta a evitar: com os anteriores ainda na janela, fecha 3/4 de novo
    # -> reabre a conversa
    message = _feed(runner, _SPEED_PLANNED, _AVOIDED)

    assert message is not None


def test_below_threshold_stays_silent():

    runner = make_runner()

    _feed(runner, _SPEED_PLANNED, _AVOIDED)
    _feed(runner, _SPEED_PLANNED, _DONE)
    message = _feed(runner, _SPEED_PLANNED, _AVOIDED)  # [T,F,T] = 2/3

    assert message is None


def test_external_coach_is_never_nudged():

    runner = make_runner(external_coach=True)

    for _ in range(5):

        assert _feed(runner, _SPEED_PLANNED, _AVOIDED) is None


def test_non_quality_workout_is_ignored():
    """Rodagem planejada não entra no detector (nem grava padrão)."""

    runner = make_runner()

    for _ in range(5):

        result = ProactiveAversionDetector.after_feedback(
            runner,
            make_planned_session(workout_type="EASY"),
            make_enriched_activity(training_type="RODAGEM"),
        )

        assert result is None
