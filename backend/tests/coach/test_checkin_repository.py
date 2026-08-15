from datetime import date, datetime, timedelta

from app.domain.entities.daily_checkin import DailyCheckin
from app.infrastructure.persistence.checkin_repository import (
    CheckinRepository,
)

TODAY = date(2026, 7, 25)


def _repo(tmp_path):

    repo = CheckinRepository()

    repo.storage = tmp_path

    return repo


def _checkin(day: date, **fields) -> DailyCheckin:

    at = datetime.combine(day, datetime.min.time()).replace(hour=8)

    return DailyCheckin(day=day.isoformat(), at=at.isoformat(), **fields)


def test_missing_profile_is_empty(tmp_path):

    assert _repo(tmp_path).load("ninguem") == []


def test_record_and_load_roundtrip(tmp_path):

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY - timedelta(days=1), energy=2))
    repo.record("renato", _checkin(TODAY, energy=4, sleep_quality=5))

    stored = repo.load("renato")

    assert [c.energy for c in stored] == [2, 4]


def test_same_day_merges_fields(tmp_path):
    """Segundo relato do mesmo dia COMPLETA o primeiro (não apaga)."""

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY, sleep_quality=2))
    # mais tarde no mesmo dia: "e a perna tá doendo"
    repo.record("renato", _checkin(TODAY, soreness=4, note="panturrilha direita"))

    stored = repo.load("renato")

    assert len(stored) == 1
    assert stored[0].sleep_quality == 2      # preservado
    assert stored[0].soreness == 4           # adicionado
    assert stored[0].note == "panturrilha direita"


def test_latest_recent_returns_recent_state(tmp_path):

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY, energy=2))

    recent = repo.latest_recent("renato", TODAY.isoformat())

    assert recent is not None
    assert recent.energy == 2


def test_latest_recent_ignores_stale_state(tmp_path):
    """Sensação é transitória: um check-in de 5 dias atrás não vale pra hoje."""

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY - timedelta(days=5), energy=1))

    assert repo.latest_recent("renato", TODAY.isoformat()) is None


def test_latest_recent_none_when_empty_state(tmp_path):
    """Check-in recente mas sem nenhum dado útil -> None (nada a injetar)."""

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY, note=""))

    assert repo.latest_recent("renato", TODAY.isoformat()) is None


def test_recent_illness_holds_for_a_few_days(tmp_path):
    """Doença dura dias: um relato de 3 dias atrás ainda segura o 'pode puxar'."""

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY - timedelta(days=3), illness=True,
                                   note="gripe"))

    ill = repo.recent_illness("renato", TODAY.isoformat())

    assert ill is not None
    assert ill.illness is True


def test_recent_illness_expires_after_window(tmp_path):

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY - timedelta(days=6), illness=True))

    assert repo.recent_illness("renato", TODAY.isoformat()) is None


def test_recent_illness_ignores_non_illness_checkins(tmp_path):

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY, soreness=4, note="perna"))

    assert repo.recent_illness("renato", TODAY.isoformat()) is None


def test_recent_concern_catches_illness_and_pain(tmp_path):
    """A queixa a acompanhar = doença OU dor moderada+ (não dor leve)."""

    repo = _repo(tmp_path)

    repo.record("ana", _checkin(TODAY - timedelta(days=2), illness=True))
    assert repo.recent_concern("ana", TODAY.isoformat()) is not None

    repo.record("bia", _checkin(TODAY - timedelta(days=2), soreness=4,
                                note="joelho"))
    c = repo.recent_concern("bia", TODAY.isoformat())
    assert c is not None and c.note == "joelho"


def test_recent_concern_ignores_light_soreness(tmp_path):

    repo = _repo(tmp_path)

    repo.record("ana", _checkin(TODAY - timedelta(days=1), soreness=2))

    assert repo.recent_concern("ana", TODAY.isoformat()) is None


def test_recent_concern_expires(tmp_path):

    repo = _repo(tmp_path)

    repo.record("ana", _checkin(TODAY - timedelta(days=9), illness=True))

    assert repo.recent_concern("ana", TODAY.isoformat()) is None


def test_merge_keeps_illness_flag(tmp_path):
    """Relatou gripe de manhã; à tarde fala de sono — a gripe NÃO se apaga."""

    repo = _repo(tmp_path)

    repo.record("renato", _checkin(TODAY, illness=True, note="gripado"))
    repo.record("renato", _checkin(TODAY, sleep_quality=2))

    stored = repo.load("renato")

    assert len(stored) == 1
    assert stored[0].illness is True
    assert stored[0].sleep_quality == 2
