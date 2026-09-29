from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.application.coach.intelligence.absence_window import AbsenceWindow

MODULE = "app.application.coach.intelligence.absence_window"


def _entry(category, content, created="2026-09-29T15:21:19-03:00", expires=None):

    return SimpleNamespace(
        category=category, content=content,
        created_at=created, expires_at=expires, status="active",
    )


def _open(entries, today):

    repo = SimpleNamespace(active=lambda profile: entries)

    with patch(f"{MODULE}.RunnerMemoryRepository", return_value=repo):

        return AbsenceWindow.open("renato", today)


def test_declared_pause_is_open_until_the_last_day():

    pause = _entry(
        "disponibilidade", "Sem treinar de 29/09 a 05/10 (7 dias)", expires="2026-10-05",
    )

    window = _open([pause], date(2026, 10, 3))

    assert window is not None
    assert window.until == date(2026, 10, 5)
    assert _open([pause], date(2026, 10, 5)) is not None
    assert _open([pause], date(2026, 10, 6)) is None


def test_legacy_pause_without_expires_at_is_deduced_from_the_text():

    legacy = _entry("disponibilidade", "Vai se ausentar dos treinos por 7 dias")

    assert _open([legacy], date(2026, 10, 2)).until == date(2026, 10, 5)


def test_routine_and_preferences_are_not_absences():

    entries = [
        _entry("disponibilidade", "Corre ter/qui/sáb pela manhã"),
        _entry("preferencia", "Ausente de treino forte às segundas"),
    ]

    assert _open(entries, date(2026, 10, 1)) is None


def test_the_latest_ending_pause_wins():

    a = _entry("disponibilidade", "Viaja até 02/10, sem correr", expires="2026-10-02")
    b = _entry("disponibilidade", "Afastado até 09/10 por repouso", expires="2026-10-09")

    assert _open([a, b], date(2026, 10, 1)).until == date(2026, 10, 9)


def test_unreadable_memory_never_breaks_the_caller():

    class Boom:

        def active(self, profile):

            raise OSError("arquivo corrompido")

    with patch(f"{MODULE}.RunnerMemoryRepository", return_value=Boom()):

        assert AbsenceWindow.open("renato", date(2026, 10, 1)) is None
