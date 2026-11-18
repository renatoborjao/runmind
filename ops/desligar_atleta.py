"""Desliga UM atleta da base (roda na VM, dentro de ~/runmind/backend).

1. bloqueia (auth/blocked_athletes.json): mensagem não reabre cadastro, sessão
   antiga do app cai em 401 — só volta por CONVITE no app;
2. backup .tgz em ~/runmind-backups/ e move TODOS os arquivos dele pra
   ~/atletas_desligados/<atleta>/ (mesmos caminhos), tirando-o de todo job.

Sem --apply só mostra o que faria. Com --only-block só grava o bloqueio (atleta
cujos arquivos já saíram: lê o perfil em ~/atletas_desligados/<atleta>/).
Religar: bash ops/desligar_atleta.sh <atleta> --unblock (só tira o bloqueio; os
arquivos antigos ficam guardados — volta como conta nova pelo convite)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from app.core.clock import now_local  # noqa: E402
from app.infrastructure.persistence.blocked_athlete_repository import (  # noqa: E402
    BlockedAthleteRepository,
)

STORAGE = Path.cwd() / "storage"
PARKED = Path.home() / "atletas_desligados"
BACKUPS = Path.home() / "runmind-backups"

# arquivos COMPARTILHADOS que citam o atleta mas não são dele: ficam
SHARED = {"auth", "dispatch_log", "sanity_audit"}


def athlete_files(slug: str) -> list[Path]:

    found = []

    for p in STORAGE.rglob(f"{slug}*"):

        rel = p.relative_to(STORAGE)

        if rel.parts[0] in SHARED:

            continue

        name = p.name.split(".")[0]

        # "joaosoares", "joaosoares_tokens", "joaosoares_summary" — não "joaosoares2"
        if name != slug and not name.startswith(f"{slug}_"):

            continue

        if any(parent in found for parent in p.parents):

            continue

        found.append(p)

    return sorted(found)


def main() -> None:

    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only-block", action="store_true")
    ap.add_argument("--unblock", action="store_true")
    ap.add_argument("--motivo", default="")
    a = ap.parse_args()

    slug = a.profile
    repo = BlockedAthleteRepository()

    if a.unblock:

        print("bloqueio removido" if repo.unblock(slug) else "não estava bloqueado")

        return

    live = STORAGE / "profiles" / f"{slug}.json"
    parked = PARKED / slug / "profiles" / f"{slug}.json"
    source = live if live.exists() else parked

    if not source.exists():

        sys.exit(f"perfil de {slug} não encontrado (nem no storage nem em {PARKED})")

    profile = json.loads(source.read_text(encoding="utf-8"))
    files = [] if a.only_block else athlete_files(slug)

    print(f"atleta: {profile.get('name')} ({slug})")
    print(f"bloqueio: telegram={'sim' if profile.get('telegram_id') else 'não'} "
          f"telefone={'sim' if profile.get('phone') else 'não'} "
          f"e-mail={'sim' if profile.get('email') else 'não'}")
    print(f"arquivos a guardar: {len(files)}")

    if not a.apply:

        print("(dry-run — nada mudou; use --apply)")

        return

    repo.block(slug, profile, reason=a.motivo)

    print("bloqueado ✔")

    if not files:

        return

    BACKUPS.mkdir(exist_ok=True)

    tgz = BACKUPS / f"desligado_{slug}_{now_local():%Y%m%d_%H%M}.tgz"

    subprocess.run(
        ["tar", "czf", str(tgz), "-C", str(STORAGE),
         *[str(f.relative_to(STORAGE)) for f in files]],
        check=True,
    )

    for f in files:

        dest = PARKED / slug / f.relative_to(STORAGE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))

    print(f"backup: {tgz}")
    print(f"guardados em: {PARKED / slug}")


if __name__ == "__main__":

    main()
