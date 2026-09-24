"""Trocar treino de dia PELO APP: o atleta confirma ("tem certeza?") e, se tem
Garmin, a semana já vai pro relógio na hora. Falha do Garmin não desfaz a troca
e cai na rede de segurança do relógio (nunca limbo)."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.security.session_token import SessionToken
from app.main import app

client = TestClient(app)


def _plan():
    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="base", weekly_volume=28,
        running_days=["Tuesday", "Thursday", "Saturday"],
        week_start=date(2026, 9, 21),
        sessions=[PlannedSession(
            day="Tuesday", workout_type="Intervalado", objective="tiro",
            planned_distance_km=8, planned_duration_minutes=None,
            target_pace_min="4:40", target_pace_max="4:50",
        )],
    )


class _Conv:
    turns: list = []

    def append_turn(self, profile, role, text):
        _Conv.turns.append((role, text))


@pytest.fixture
def env(monkeypatch):
    _Conv.turns = []
    calls = {"push": 0, "offer": 0}

    monkeypatch.setattr(
        "app.infrastructure.persistence.weekly_plan_repository.WeeklyPlanRepository.load",
        lambda self, profile: _plan(),
    )
    monkeypatch.setattr(
        "app.application.coach.conversation.plan_change_applier.PlanChangeApplier.apply",
        staticmethod(lambda profile, proposal: _plan()),
    )
    monkeypatch.setattr(
        "app.infrastructure.persistence.conversation_repository.ConversationRepository", _Conv,
    )
    monkeypatch.setattr(
        "app.core.clock.now_local", lambda: datetime(2026, 9, 22, 8, 0),
    )

    def offer(profile):
        calls["offer"] += 1
        return "\n\n⌚ Quer que eu atualize? Responde *sim*."

    monkeypatch.setattr("app.application.garmin.watch_offer.watch_update_offer", offer)
    return monkeypatch, calls


def _connect(mp, connected: bool):
    mp.setattr(
        "app.infrastructure.integrations.garmin.garmin_client.GarminClient.is_connected",
        staticmethod(lambda profile: connected),
    )


def _push(mp, calls, *, raises=False, results=None):
    async def fake(profile, *a, **k):
        calls["push"] += 1
        if raises:
            raise RuntimeError("garmin fora")
        return None, None, results if results is not None else [{"ok": True}]

    mp.setattr("app.application.garmin.push_current_plan.push_current_plan", fake)


def _move():
    return client.post(
        "/api/v1/plan/move",
        json={"from_day": "Tuesday", "to_day": "Wednesday"},
        cookies={"rm_session": SessionToken.issue("renato2")},
    )


def test_move_with_garmin_pushes_watch(env):
    mp, calls = env
    _connect(mp, True)
    _push(mp, calls)

    r = _move()

    assert r.status_code == 200
    assert r.json()["watch"] == "sent"
    assert calls["push"] == 1
    assert "Relógio atualizado" in r.json()["message"]
    assert "Já atualizei teu relógio" in _Conv.turns[-1][1]


def test_move_without_garmin_does_not_push(env):
    mp, calls = env
    _connect(mp, False)
    _push(mp, calls)

    r = _move()

    assert r.json()["watch"] == "none"
    assert calls["push"] == 0
    assert "relógio" not in _Conv.turns[-1][1].lower()


def test_garmin_failure_keeps_move_and_arms_safety_net(env):
    mp, calls = env
    _connect(mp, True)
    _push(mp, calls, raises=True)

    r = _move()

    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["watch"] == "failed"
    assert calls["offer"] == 1  # rede de segurança armada (o 'sim' no chat reenvia)
    assert "Responde *sim*" in _Conv.turns[-1][1]


def test_nothing_uploaded_counts_as_failure(env):
    mp, calls = env
    _connect(mp, True)
    _push(mp, calls, results=[{"ok": False}])

    assert _move().json()["watch"] == "failed"
