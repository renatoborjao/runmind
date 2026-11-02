"""ARQUIVO PERMANENTE (nº 91). Vários repositórios guardavam só uma janela e apagavam o resto: as
últimas 200 mensagens, 60 dias de diário, 10 mensagens enviadas, 26 leituras do corpo, as análises
mais antigas, a versão do plano que o coach jogava fora ao refazer a semana. Renato (01/11): "todo
o histórico nós devemos guardar e não perder nada — o coach analisa e monta o plano".

Duas garantias testadas: o que sai da janela vai pro arquivo (que só cresce), e se arquivar falhar
a janela fica INTEIRA — melhor um arquivo maior que um registro perdido."""

from datetime import date
from unittest.mock import patch

from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.readiness_diary_entry import ReadinessDiaryEntry
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence import conversation_repository
from app.infrastructure.persistence.coach_outbox_repository import CoachOutboxRepository
from app.infrastructure.persistence.conversation_repository import ConversationRepository
from app.infrastructure.persistence.permanent_archive import PermanentArchive
from app.infrastructure.persistence.readiness_diary_repository import ReadinessDiaryRepository
from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository
from app.infrastructure.persistence import workout_analysis_repository
from app.infrastructure.persistence.workout_analysis_repository import WorkoutAnalysisRepository


def _archived(storage, kind, profile="atleta"):

    return PermanentArchive.load(storage, kind, profile)


# ------------------------------------------------------------------ a peça central


def test_what_leaves_the_window_goes_to_the_archive_in_order(tmp_path):

    storage = tmp_path / "coisa"

    window = PermanentArchive.trim_list(storage, "coisa", "atleta", [1, 2, 3, 4, 5], 2)

    assert window == [4, 5]
    assert [e["record"] for e in _archived(storage, "coisa")] == [1, 2, 3]
    assert all(e["archived_at"] and e["reason"] for e in _archived(storage, "coisa"))


def test_the_archive_only_grows_and_a_second_trim_adds_after_the_first(tmp_path):

    storage = tmp_path / "coisa"

    PermanentArchive.trim_list(storage, "coisa", "atleta", [1, 2, 3], 2)
    PermanentArchive.trim_list(storage, "coisa", "atleta", [3, 4, 5], 2)

    assert [e["record"] for e in _archived(storage, "coisa")] == [1, 3]


def test_newest_first_lists_drop_the_tail(tmp_path):

    storage = tmp_path / "coisa"

    window = PermanentArchive.trim_list(
        storage, "coisa", "atleta", ["novo", "meio", "velho"], 2, newest_first=True,
    )

    assert window == ["novo", "meio"]
    assert [e["record"] for e in _archived(storage, "coisa")] == ["velho"]


def test_below_the_window_nothing_is_written(tmp_path):

    storage = tmp_path / "coisa"

    assert PermanentArchive.trim_list(storage, "coisa", "atleta", [1, 2], 5) == [1, 2]
    assert _archived(storage, "coisa") == []


def test_if_archiving_fails_the_window_stays_whole(tmp_path):
    """Melhor um arquivo maior que um registro perdido."""

    storage = tmp_path / "coisa"

    with patch.object(PermanentArchive, "append", return_value=False):

        assert PermanentArchive.trim_list(storage, "coisa", "atleta", [1, 2, 3, 4], 2) == [1, 2, 3, 4]

        data = {"a": {"date": "2026-01-01"}, "b": {"date": "2026-02-01"}, "c": {"date": "2026-03-01"}}

        assert PermanentArchive.trim_dict(storage, "coisa", "atleta", data, 1) == data


def test_a_dictionary_keeps_the_most_recent_by_date_and_archives_the_rest(tmp_path):

    storage = tmp_path / "coisa"

    data = {"a": {"date": "2026-01-01"}, "b": {"date": "2026-03-01"}, "c": {"date": "2026-02-01"}}

    window = PermanentArchive.trim_dict(storage, "coisa", "atleta", data, 2)

    assert set(window) == {"b", "c"}
    assert [e["record"] for e in _archived(storage, "coisa")] == [
        {"key": "a", "value": {"date": "2026-01-01"}},
    ]


def test_an_unreadable_line_is_skipped_and_a_missing_file_is_empty(tmp_path):

    storage = tmp_path / "coisa"

    assert PermanentArchive.load(storage, "coisa", "atleta") == []

    PermanentArchive.append(storage, "coisa", "atleta", [{"ok": 1}], "x")

    with open(PermanentArchive.file(storage, "coisa", "atleta"), "a", encoding="utf-8") as f:

        f.write("isto não é json" + chr(10))

    assert [e["record"] for e in PermanentArchive.load(storage, "coisa", "atleta")] == [{"ok": 1}]


# ------------------------------------------------------------------ os repositórios


def test_conversation_turns_beyond_the_window_are_kept_in_the_archive(tmp_path):

    repo = ConversationRepository()
    repo.storage = tmp_path / "conversations"
    repo.storage.mkdir()

    with patch.object(conversation_repository, "MAX_TURNS_PERSISTED", 3):

        for i in range(5):

            repo.append_turn("atleta", "user", f"mensagem {i}")

    assert [t["text"] for t in repo.load("atleta")] == ["mensagem 2", "mensagem 3", "mensagem 4"]
    assert [e["record"]["text"] for e in _archived(repo.storage, "conversations")] == [
        "mensagem 0", "mensagem 1",
    ]


def test_conversation_is_not_trimmed_when_the_archive_is_unavailable(tmp_path):

    repo = ConversationRepository()
    repo.storage = tmp_path / "conversations"
    repo.storage.mkdir()

    with patch.object(conversation_repository, "MAX_TURNS_PERSISTED", 2), patch.object(
        PermanentArchive, "append", return_value=False,
    ):

        for i in range(4):

            repo.append_turn("atleta", "user", f"mensagem {i}")

    assert len(repo.load("atleta")) == 4


def _entry(day, tier="BRAKE"):

    return ReadinessDiaryEntry(
        day=day, at=f"{day}T09:00:00-03:00", tier=tier, body_state="STRAINED",
        reason="r", demand="demanding", would_notify=True, from_tier=None,
    )


def test_readiness_diary_keeps_the_replaced_reading_and_the_old_days(tmp_path):

    repo = ReadinessDiaryRepository()
    repo.storage = tmp_path / "readiness_diary"
    repo.storage.mkdir()

    repo.record("atleta", _entry("2026-10-01", tier="WATCH"))
    repo.record("atleta", _entry("2026-10-01", tier="BRAKE"))        # mesmo dia: substitui

    archived = _archived(repo.storage, "readiness_diary")

    assert [e["record"]["tier"] for e in archived] == ["WATCH"]
    assert archived[0]["reason"] == "substituída no mesmo dia"

    with patch("app.infrastructure.persistence.readiness_diary_repository._MAX", 2):

        for day in ("2026-10-02", "2026-10-03", "2026-10-04"):

            repo.record("atleta", _entry(day))

    assert [e.day for e in repo.load("atleta")] == ["2026-10-03", "2026-10-04"]

    days = [e["record"]["day"] for e in _archived(repo.storage, "readiness_diary")]

    assert days == ["2026-10-01", "2026-10-01", "2026-10-02"]


def test_coach_outbox_keeps_every_message_it_ever_sent(tmp_path):

    repo = CoachOutboxRepository()
    repo.storage = tmp_path / "coach_outbox"
    repo.storage.mkdir()

    with patch("app.infrastructure.persistence.coach_outbox_repository._MAX_ENTRIES", 2):

        for i in range(4):

            repo.append("atleta", f"texto {i}")

    assert [e["text"] for e in repo.recent("atleta", 10)] == ["texto 2", "texto 3"]
    assert [e["record"]["text"] for e in _archived(repo.storage, "coach_outbox")] == ["texto 0", "texto 1"]


def _plan(week, km, kind="Rodagem"):

    session = PlannedSession(
        day="Tuesday", workout_type=kind, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=None, target_pace_max=None,
    )

    return TrainingPlan(
        athlete_name="A", objective="meia", phase="BASE", weekly_volume=km,
        running_days=["Tuesday"], week_start=week, sessions=[session],
    )


def test_a_redone_week_keeps_the_version_the_coach_threw_away(tmp_path):
    """Renato 01/11: o plano de 20,7 km (descarga) foi refeito para 30 km; a versão que ensinou
    tudo só existe porque foi copiada à mão."""

    repo = WeeklyPlanRepository()
    repo.storage = tmp_path / "plans"
    repo.storage.mkdir()

    week = date(2026, 11, 2)

    repo.save("atleta", _plan(week, 20.7))
    repo.save("atleta", _plan(week, 20.7))          # igual: nada a guardar
    repo.save("atleta", _plan(week, 30.0))          # refeito: a de 20,7 vai pro arquivo

    assert [p.weekly_volume for p in repo.history("atleta")] == [30.0]

    versions = _archived(repo.storage, "plan_versions")

    assert [v["record"]["weekly_volume"] for v in versions] == [20.7]
    assert versions[0]["reason"] == "versão substituída (refeito/ajustado)"


def test_a_reprocessed_workout_keeps_the_previous_analysis_and_old_ones_are_archived(tmp_path):

    repo = WorkoutAnalysisRepository()
    repo.storage = tmp_path / "workout_analysis"
    repo.storage.mkdir()

    repo.record("atleta", 1, "2026-10-01", 10.0, "primeira leitura")
    repo.record("atleta", 1, "2026-10-01", 10.0, "segunda leitura")

    replaced = _archived(repo.storage, "workout_analysis")

    assert [e["record"]["value"]["analysis"] for e in replaced] == ["primeira leitura"]

    with patch.object(workout_analysis_repository, "_MAX_ENTRIES", 2):

        repo.record("atleta", 2, "2026-10-08", 5.0, "b")
        repo.record("atleta", 3, "2026-10-15", 6.0, "c")

    assert set(repo._load("atleta")) == {"2", "3"}

    keys = [e["record"]["key"] for e in _archived(repo.storage, "workout_analysis")]

    assert keys == ["1", "1"]            # a versão substituída e, depois, a que saiu da janela
