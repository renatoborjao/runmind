"""Backup automático do storage/ — a rede de segurança dos dados dos
atletas (perfis, histórico, memória evolutiva, conversas, tokens Garmin/
Strava). Tudo vive em arquivo no disco do Renato e NÃO é versionado
(storage/ está no .gitignore); sem backup, um disco corrompido ou uma
exclusão acidental levaria tudo, sem volta.

Tira um snapshot .zip do storage/ inteiro, com rotação (mantém os últimos
N). Aponte BACKUP_DIR pra uma pasta sincronizada (OneDrive/Google Drive)
pra ter cópia FORA da máquina de graça — senão o backup mora no mesmo
disco e só protege contra corrupção/exclusão, não contra o disco morrer.
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path


class StorageBackup:

    # prefixo dos snapshots — usado pra rotacionar sem tocar em outros
    # arquivos que por acaso estejam na pasta de backup
    PREFIX = "runmind-storage-"

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        backup_dir: str | Path | None = None,
        keep: int = 28,
    ) -> None:

        # backend/ (…/app/infrastructure/backup/storage_backup.py -> parents[3])
        base = Path(__file__).resolve().parents[3]

        self.storage_dir = (
            Path(storage_dir) if storage_dir else base / "storage"
        )

        self.backup_dir = (
            Path(backup_dir) if backup_dir else base / "backups"
        )

        # sempre mantém pelo menos 1 snapshot
        self.keep = max(1, keep)

    def run(self) -> Path | None:
        """Cria um snapshot .zip do storage/ e rotaciona. Retorna o caminho
        do zip, ou None se não há nada pra salvar (storage vazio/ausente)."""

        if not self.storage_dir.exists() or not any(
            self.storage_dir.iterdir()
        ):

            return None

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # microssegundos no nome pra dois snapshots no mesmo segundo não
        # se sobrescreverem (acontece em teste e em restart rápido)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")

        base_name = self.backup_dir / f"{self.PREFIX}{stamp}"

        archive = shutil.make_archive(
            str(base_name),
            "zip",
            root_dir=self.storage_dir,
        )

        self._rotate()

        return Path(archive)

    def has_recent_snapshot(self, within: timedelta) -> bool:
        """True se já existe um snapshot mais novo que `within`. Usado pelo
        tick do scheduler pra não duplicar backup em restarts rápidos (ex.:
        hot-reload do uvicorn em dev reinicia o processo a cada arquivo
        salvo) — não afeta `run()`, que o backup manual (backup_now.py)
        continua chamando direto pra sempre forçar um snapshot."""

        snapshots = sorted(self.backup_dir.glob(f"{self.PREFIX}*.zip"))

        if not snapshots:

            return False

        newest = snapshots[-1]

        age = datetime.now() - datetime.fromtimestamp(
            newest.stat().st_mtime
        )

        return age < within

    def _rotate(self) -> None:
        """Mantém só os últimos `keep` snapshots; apaga os mais antigos.
        A ordem lexicográfica do nome (timestamp) = ordem cronológica."""

        snapshots = sorted(self.backup_dir.glob(f"{self.PREFIX}*.zip"))

        for old in snapshots[: -self.keep]:

            old.unlink(missing_ok=True)
