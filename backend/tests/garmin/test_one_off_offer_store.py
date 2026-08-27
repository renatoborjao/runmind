import json
from datetime import date

from app.infrastructure.integrations.garmin.one_off_offer_store import (
    OneOffOfferStore,
)

MOD = "app.infrastructure.integrations.garmin.one_off_offer_store"

ON = date(2026, 8, 31)


def _use_tmp(monkeypatch, tmp_path):

    monkeypatch.setattr(f"{MOD}._STORAGE", tmp_path)


def test_set_pending_keeps_date_and_allows_reminder(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    OneOffOfferStore.set_pending("renato", ON)

    assert OneOffOfferStore.pending_date("renato") == ON
    assert OneOffOfferStore.reminder_due("renato", min_age_seconds=0)


def test_reminder_not_due_before_min_age(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    OneOffOfferStore.set_pending("renato", ON)

    assert not OneOffOfferStore.reminder_due("renato", min_age_seconds=3600)


def test_mark_reminded_blocks_but_keeps_pending(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    OneOffOfferStore.set_pending("renato", ON)
    OneOffOfferStore.mark_reminded("renato")

    assert OneOffOfferStore.pending_date("renato") == ON  # segue viva pro "sim"
    assert not OneOffOfferStore.reminder_due("renato", min_age_seconds=0)


def test_clear_removes_offer(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    OneOffOfferStore.set_pending("renato", ON)
    OneOffOfferStore.clear("renato")

    assert OneOffOfferStore.pending_date("renato") is None
    assert not OneOffOfferStore.reminder_due("renato", min_age_seconds=0)


def test_expired_offer_is_gone(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    old = 1000.0
    (tmp_path / "renato.json").write_text(
        json.dumps({"ts": old, "date": ON.isoformat(), "reminded": False}),
        encoding="utf-8",
    )

    monkeypatch.setattr(f"{MOD}.time.time", lambda: old + 24 * 3600)  # TTL 12h

    assert OneOffOfferStore.pending_date("renato") is None
    assert not OneOffOfferStore.reminder_due("renato", min_age_seconds=0)


def test_legacy_payload_without_reminded_still_works(monkeypatch, tmp_path):

    _use_tmp(monkeypatch, tmp_path)

    now = 5000.0
    (tmp_path / "renato.json").write_text(
        json.dumps({"ts": now - 4 * 3600, "date": ON.isoformat()}),
        encoding="utf-8",
    )

    monkeypatch.setattr(f"{MOD}.time.time", lambda: now)

    assert OneOffOfferStore.pending_date("renato") == ON
    assert OneOffOfferStore.reminder_due("renato", min_age_seconds=3 * 3600)
