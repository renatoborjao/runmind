"""Percepção do atleta: relógio, resposta e conversa gravam no MESMO lugar."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.application.coach.conversation.coach_brain import CoachBrain
from app.application.coach.intelligence.perception_recorder import (
    PerceptionRecorder,
)
from app.infrastructure.persistence.session_rpe_repository import (
    SessionRpeRepository,
)
from tests.coach.factories import make_activity

MODULE = "app.application.coach.intelligence.perception_recorder"

TODAY = date(2026, 9, 27)


@pytest.fixture
def repo(tmp_path, monkeypatch):

    instance = SessionRpeRepository()

    instance.storage = tmp_path

    monkeypatch.setattr(f"{MODULE}.SessionRpeRepository", lambda: instance)

    monkeypatch.setattr(f"{MODULE}.today_local", lambda: TODAY)

    return instance


def _watch_run(rpe=60, feel=25, **kw):

    activity = make_activity(
        id=kw.pop("id", 77), moving_time=3000,
        start_date=kw.pop("start_date", datetime(2026, 9, 26, 7, 0)), **kw,
    )

    metrics = {}

    if rpe is not None:

        metrics["workout_rpe"] = rpe

    if feel is not None:

        metrics["workout_feel"] = feel

    activity.raw = {"_garmin_metrics": metrics}

    return activity


# ---- relógio ------------------------------------------------------------


def test_watch_self_evaluation_is_recorded(repo):

    assert PerceptionRecorder.from_watch("renato", _watch_run()) is True

    [session] = repo.load_sessions("renato")

    assert session.rpe == 6
    assert session.srpe == 300.0
    assert session.feel == "sentiu-se cansado"
    assert session.source == "relógio"
    assert session.day == "2026-09-26"


def test_watch_without_self_evaluation_records_nothing(repo):

    assert PerceptionRecorder.from_watch("renato", _watch_run(rpe=None)) is False

    assert repo.load_sessions("renato") == []


# ---- conversa -----------------------------------------------------------


def test_chat_perception_records_for_the_run_of_that_day(repo):

    run = _watch_run()

    with patch(f"{MODULE}.PerceptionRecorder._run_on", return_value=run):

        ok = PerceptionRecorder.from_chat(
            "renato", {"day": "2026-09-26", "rpe": 8, "feel": "morri no fim"},
        )

    assert ok is True

    [session] = repo.load_sessions("renato")

    assert session.rpe == 8 and session.source == "conversa"
    assert session.note == "morri no fim"


def test_chat_words_enrich_the_watch_record(repo):
    """O relógio deu o número; a conversa soma as PALAVRAS dele sem perder o
    número nem a sensação do relógio."""

    run = _watch_run()

    PerceptionRecorder.from_watch("renato", run)

    with patch(f"{MODULE}.PerceptionRecorder._run_on", return_value=run):

        PerceptionRecorder.from_chat(
            "renato", {"day": "2026-09-26", "rpe": None, "feel": "perna pesada"},
        )

    [session] = repo.load_sessions("renato")

    assert session.rpe == 6
    assert session.feel == "sentiu-se cansado"
    assert session.note == "perna pesada"
    assert session.source == "relógio"


@pytest.mark.parametrize("day", ["2026-09-28", "2026-09-10", "ontem", ""])
def test_chat_perception_ignores_future_old_or_invalid_days(repo, day):

    with patch(f"{MODULE}.PerceptionRecorder._run_on", return_value=_watch_run()):

        assert PerceptionRecorder.from_chat(
            "renato", {"day": day, "rpe": 7, "feel": None},
        ) is False


def test_chat_perception_without_a_run_that_day_records_nothing(repo):

    with patch(f"{MODULE}.PerceptionRecorder._run_on", return_value=None):

        assert PerceptionRecorder.from_chat(
            "renato", {"day": "2026-09-26", "rpe": 7, "feel": None},
        ) is False


def test_pending_line_names_the_training_day(repo):

    repo.set_pending(
        "renato", activity_id=1, day="2026-09-26", duration_min=50.0,
    )

    line = PerceptionRecorder.pending_line("renato")

    assert "26/09" in line and "perception" in line


def test_no_pending_no_line(repo):

    assert PerceptionRecorder.pending_line("renato") == ""


# ---- cérebro ------------------------------------------------------------


def test_brain_parses_perception():

    decision = CoachBrain._parse(
        '{"say": "Boa!", "perception": {"day": "2026-09-26", "rpe": 7, '
        '"feel": "puxado"}}'
    )

    assert decision.perception == {"day": "2026-09-26", "rpe": 7, "feel": "puxado"}


@pytest.mark.parametrize("raw", [
    'null', '"sim"', '{"day": "2026-09-26"}', '{"rpe": 7}', '{"day": "26/9", "rpe": 7}',
])
def test_brain_drops_unusable_perception(raw):

    decision = CoachBrain._parse('{"say": "ok", "perception": ' + raw + '}')

    assert decision.perception is None


# ---- pós-treino ---------------------------------------------------------


def test_watch_perception_skips_the_rpe_question():
    """Se o atleta já marcou no relógio, a análise não pergunta de novo."""

    from app.application.events.training_completed import TrainingCompletedEvent

    enriched = MagicMock()
    enriched.activity = _watch_run()

    with (
        patch(f"{MODULE}.PerceptionRecorder.from_watch", return_value=True),
        patch(
            "app.application.events.training_completed.SessionRpeRepository"
        ) as rpe_repo,
    ):

        out = TrainingCompletedEvent._ask_rpe(
            "renato", {"activity": enriched}, "análise",
        )

    assert out == "análise"
    rpe_repo.return_value.set_pending.assert_not_called()
