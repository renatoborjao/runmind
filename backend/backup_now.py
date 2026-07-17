"""Backup manual do storage/ sob demanda (o mesmo que o scheduler roda a
cada 6h). Útil antes de mexer em algo arriscado.

Uso:  python backup_now.py
"""

from app.core.config import get_settings
from app.infrastructure.backup.storage_backup import StorageBackup


def main() -> None:

    settings = get_settings()

    backup = StorageBackup(
        backup_dir=settings.backup_dir or None,
        keep=settings.backup_keep,
    )

    path = backup.run()

    if path is None:

        print("Nada pra salvar (storage/ vazio ou ausente).")

        return

    print(f"Backup criado: {path}")

    print(f"Pasta de backups: {backup.backup_dir}")


if __name__ == "__main__":

    main()
