"""Perfil-esqueleto (cadastro pelo app antes do wizard: onboarding_complete=False,
idade 0, sem objetivo) nunca entra nos jobs de fundo — sem plano de domingo,
briefing, poll ou proativo pra quem ainda não terminou o cadastro."""

import json
import re
from pathlib import Path

from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

_BASE = dict(
    id="runner-1", name="Renato", age=30, weight=70.0, height=175.0,
    goal="10k", weekly_training_days=3, phone="+5511900000000",
)


def _repo(tmp_path, **profiles):
    for name, extra in profiles.items():
        (tmp_path / f"{name}.json").write_text(
            json.dumps({**_BASE, **extra}), encoding="utf-8",
        )
    repo = RunnerProfileRepository()
    repo.storage = tmp_path
    return repo


def test_list_active_skips_skeleton_profiles(tmp_path):
    repo = _repo(
        tmp_path,
        renato2={"onboarding_complete": True},
        novato={"onboarding_complete": False, "age": 0, "goal": ""},
    )

    assert repo.list_active() == ["renato2"]
    assert sorted(repo.list_all()) == ["novato", "renato2"]  # slug/cadastro seguem vendo


def test_legacy_profile_without_the_flag_counts_as_active(tmp_path):
    repo = _repo(tmp_path, fernanda={})  # perfil antigo (bot), sem o campo

    assert repo.list_active() == ["fernanda"]


# ---------------------------------------------------------------------------
# trava estrutural: job novo nasce blindado. Quem percorre atletas em
# app/application usa list_active(); list_all() só onde a unicidade do slug
# precisa enxergar TODO perfil (cadastro/onboarding).
_LIST_ALL_ALLOWED = {
    "app/application/auth/signup_service.py",
    "app/application/onboarding/onboarding_flow.py",
}


def test_background_code_never_iterates_with_list_all():
    root = Path(__file__).resolve().parents[2]
    offenders = [
        path.relative_to(root).as_posix()
        for path in (root / "app" / "application").rglob("*.py")
        if re.search(r"\.list_all\(\)", path.read_text(encoding="utf-8"))
        and path.relative_to(root).as_posix() not in _LIST_ALL_ALLOWED
    ]

    assert offenders == [], (
        f"use RunnerProfileRepository().list_active() (perfil-esqueleto fora): {offenders}"
    )
