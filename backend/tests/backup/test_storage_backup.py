import zipfile
from datetime import timedelta

from app.infrastructure.backup.storage_backup import StorageBackup


def _make_storage(tmp_path):
    """storage/ de mentira com alguns arquivos aninhados."""

    storage = tmp_path / "storage"
    (storage / "profiles").mkdir(parents=True)
    (storage / "profiles" / "mauricio.json").write_text(
        '{"name": "Mauricio"}', encoding="utf-8"
    )
    (storage / "garmin" / "mauricio").mkdir(parents=True)
    (storage / "garmin" / "mauricio" / "analysis_on").write_text(
        "1", encoding="utf-8"
    )

    return storage


def test_run_creates_zip_with_storage_contents(tmp_path):

    storage = _make_storage(tmp_path)
    backup_dir = tmp_path / "backups"

    path = StorageBackup(storage, backup_dir).run()

    assert path is not None
    assert path.exists()
    assert path.suffix == ".zip"
    assert path.parent == backup_dir

    # o conteúdo do storage/ está lá dentro (caminhos relativos ao storage)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()

    assert "profiles/mauricio.json" in names
    assert "garmin/mauricio/analysis_on" in names


def test_empty_or_missing_storage_returns_none(tmp_path):

    # ausente
    missing = tmp_path / "nada"
    assert StorageBackup(missing, tmp_path / "b1").run() is None

    # vazio
    empty = tmp_path / "storage"
    empty.mkdir()
    assert StorageBackup(empty, tmp_path / "b2").run() is None


def test_rotation_keeps_only_last_n(tmp_path):

    storage = _make_storage(tmp_path)
    backup_dir = tmp_path / "backups"

    backup = StorageBackup(storage, backup_dir, keep=3)

    created = [backup.run() for _ in range(5)]

    remaining = sorted(backup_dir.glob("runmind-storage-*.zip"))

    # só os 3 últimos sobrevivem
    assert len(remaining) == 3
    assert remaining == created[-3:]


def test_keep_is_at_least_one(tmp_path):

    storage = _make_storage(tmp_path)
    backup_dir = tmp_path / "backups"

    # keep=0 não pode zerar tudo — mantém pelo menos 1
    backup = StorageBackup(storage, backup_dir, keep=0)

    backup.run()
    backup.run()

    remaining = list(backup_dir.glob("runmind-storage-*.zip"))

    assert len(remaining) == 1


def test_has_recent_snapshot_false_without_any_backup(tmp_path):

    backup = StorageBackup(tmp_path / "storage", tmp_path / "backups")

    assert backup.has_recent_snapshot(timedelta(minutes=5)) is False


def test_has_recent_snapshot_true_right_after_run(tmp_path):

    storage = _make_storage(tmp_path)
    backup = StorageBackup(storage, tmp_path / "backups")

    backup.run()

    assert backup.has_recent_snapshot(timedelta(minutes=5)) is True


def test_has_recent_snapshot_false_when_window_already_elapsed(tmp_path):

    storage = _make_storage(tmp_path)
    backup = StorageBackup(storage, tmp_path / "backups")

    backup.run()

    # janela negativa == "nada é recente o bastante" (equivalente a ter
    # passado o intervalo todo)
    assert backup.has_recent_snapshot(timedelta(seconds=-1)) is False
