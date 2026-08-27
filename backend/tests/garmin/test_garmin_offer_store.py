import json

from app.infrastructure.integrations.garmin.garmin_offer_store import (
    GarminOfferStore,
)

MOD = "app.infrastructure.integrations.garmin.garmin_offer_store"


def _use_tmp(monkeypatch, tmp_path):

    monkeypatch.setattr(f"{MOD}._STORAGE", tmp_path)


def test_set_pending_is_pending_and_not_reminded(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    GarminOfferStore.set_pending("renato")

    assert GarminOfferStore.is_pending("renato")
    # recém-criada: já poderia lembrar se não fosse a idade mínima
    assert GarminOfferStore.reminder_due("renato", min_age_seconds=0)


def test_reminder_not_due_before_min_age(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    GarminOfferStore.set_pending("renato")

    # exige 1h de idade; a oferta acabou de nascer
    assert not GarminOfferStore.reminder_due("renato", min_age_seconds=3600)


def test_mark_reminded_blocks_further_reminders_but_stays_pending(
    monkeypatch, tmp_path
):

    _use_tmp(monkeypatch, tmp_path)

    GarminOfferStore.set_pending("renato")
    GarminOfferStore.mark_reminded("renato")

    # segue válida pro "sim", mas não lembra de novo (um por episódio)
    assert GarminOfferStore.is_pending("renato")
    assert not GarminOfferStore.reminder_due("renato", min_age_seconds=0)


def test_clear_removes_offer(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    GarminOfferStore.set_pending("renato")
    GarminOfferStore.clear("renato")

    assert not GarminOfferStore.is_pending("renato")
    assert not GarminOfferStore.reminder_due("renato", min_age_seconds=0)


def test_expired_offer_is_not_pending_nor_due(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    # oferta de 3 dias atrás (TTL é 48h)
    old_ts = 1000.0
    (tmp_path / "renato.json").write_text(
        json.dumps({"ts": old_ts, "reminded": False}), encoding="utf-8"
    )

    monkeypatch.setattr(f"{MOD}.time.time", lambda: old_ts + 72 * 3600)

    assert not GarminOfferStore.is_pending("renato")
    assert not GarminOfferStore.reminder_due("renato", min_age_seconds=0)


def test_legacy_payload_without_reminded_flag_still_works(
    monkeypatch, tmp_path
):
    """Ofertas antigas gravadas como {'ts': ...} (sem 'reminded') continuam
    válidas e passíveis de lembrete."""

    _use_tmp(monkeypatch, tmp_path)

    now = 5000.0
    (tmp_path / "renato.json").write_text(
        json.dumps({"ts": now - 4 * 3600}), encoding="utf-8"
    )

    monkeypatch.setattr(f"{MOD}.time.time", lambda: now)

    assert GarminOfferStore.is_pending("renato")
    assert GarminOfferStore.reminder_due("renato", min_age_seconds=3 * 3600)


def test_reminder_not_due_without_offer(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    assert not GarminOfferStore.reminder_due("ninguem", min_age_seconds=0)
