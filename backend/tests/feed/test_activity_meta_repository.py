import base64
from io import BytesIO

import pytest
from PIL import Image

from app.infrastructure.persistence.activity_meta_repository import (
    ActivityMetaRepository,
    valid_key,
)


def _png_data_url(w=2000, h=1500) -> str:
    img = Image.new("RGB", (w, h), (10, 180, 150))
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = ActivityMetaRepository()
    r.meta_dir = tmp_path / "meta"
    r.photo_dir = tmp_path / "photos"
    r.meta_dir.mkdir(parents=True, exist_ok=True)
    return r


def test_valid_key_blocks_traversal():
    assert valid_key("arch-123")
    assert valid_key("app-abc_DEF")
    assert not valid_key("../etc/passwd")
    assert not valid_key("a/b")
    assert not valid_key("")


def test_title_set_and_prune(repo):
    repo.set_title("u", "arch-1", "Longão da Serra")
    assert repo.load("u")["arch-1"]["title"] == "Longão da Serra"
    # título vazio remove a chave inteira (sem foto)
    repo.set_title("u", "arch-1", "  ")
    assert "arch-1" not in repo.load("u")


def test_photo_compress_downscale_and_roundtrip(repo):
    repo.set_photo("u", "app-9", _png_data_url(2000, 1500))

    # gravou como JPEG e encolheu pro teto (lado maior <= 1280)
    saved = repo._photo_path("u", "app-9")
    assert saved.exists()
    img = Image.open(saved)
    assert img.format == "JPEG"
    assert max(img.size) <= 1280
    # bem menor que o PNG original de 2000x1500
    assert saved.stat().st_size < 300_000

    assert repo.load("u")["app-9"]["has_photo"] is True
    url = repo.photo_data_url("u", "app-9")
    assert url and url.startswith("data:image/jpeg;base64,")


def test_delete_photo_prunes_and_keeps_title(repo):
    repo.set_title("u", "app-9", "Prova!")
    repo.set_photo("u", "app-9", _png_data_url(400, 300))
    repo.delete_photo("u", "app-9")

    assert not repo._photo_path("u", "app-9").exists()
    # título fica; só o has_photo saiu
    entry = repo.load("u")["app-9"]
    assert entry.get("title") == "Prova!"
    assert "has_photo" not in entry


def test_rejects_oversized_upload(repo):
    with pytest.raises(ValueError):
        repo.set_photo("u", "app-x", "data:image/png;base64," + base64.b64encode(b"x" * (13 * 1024 * 1024)).decode())
