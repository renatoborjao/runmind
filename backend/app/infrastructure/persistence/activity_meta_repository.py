from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from pathlib import Path

# Só chaves de atividade do feed: "arch-<id>" / "app-<id>". Trava path traversal
# no nome do arquivo da foto.
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

# Teto do upload (antes de comprimir) e do lado maior depois de comprimir.
_MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_MAX_SIDE = 1280
_JPEG_QUALITY = 80


def valid_key(key: str) -> bool:

    return bool(key and _KEY_RE.match(key))


class ActivityMetaRepository:
    """Adornos que o atleta põe numa atividade: TÍTULO custom e FOTO. Um arquivo
    de metadados por atleta (storage/activity_meta/{profile}.json, chave ->
    {title, has_photo}) + as fotos comprimidas em disco
    (storage/activity_photos/{profile}/{key}.jpg).

    Econômico de disco de propósito (rodamos em VM free): a foto é
    redimensionada pra no máx 1280px no lado maior e salva JPEG q80 (~200 KB),
    nunca o original de celular (~5 MB). Só o feed carrega `has_photo` (booleano);
    os bytes só saem quando o detalhe pede."""

    def __init__(self):

        base = Path(__file__).resolve().parents[3] / "storage"

        self.meta_dir = base / "activity_meta"
        self.photo_dir = base / "activity_photos"

        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def _meta_file(self, profile: str) -> Path:

        return self.meta_dir / f"{profile}.json"

    def load(self, profile: str) -> dict:

        f = self._meta_file(profile)

        if not f.exists():

            return {}

        try:

            with open(f, encoding="utf-8") as fh:

                return json.load(fh)

        except (json.JSONDecodeError, OSError):

            return {}

    def _save(self, profile: str, meta: dict) -> None:

        with open(self._meta_file(profile), "w", encoding="utf-8") as fh:

            json.dump(meta, fh, ensure_ascii=False, indent=2)

    def _entry(self, meta: dict, key: str) -> dict:

        e = meta.get(key)

        return e if isinstance(e, dict) else {}

    def set_title(self, profile: str, key: str, title: str | None) -> None:

        meta = self.load(profile)

        entry = self._entry(meta, key)

        clean = (title or "").strip()[:80]

        if clean:

            entry["title"] = clean

        else:

            entry.pop("title", None)

        self._prune(meta, key, entry)

        self._save(profile, meta)

    def _photo_path(self, profile: str, key: str) -> Path:

        return self.photo_dir / profile / f"{key}.jpg"

    def set_photo(self, profile: str, key: str, data_url: str) -> None:
        """Recebe uma data URL de imagem, COMPRIME (≤1280px, JPEG q80) e salva os
        bytes em disco. Lazy import do Pillow (só quando alguém sobe foto)."""

        from PIL import Image  # noqa: PLC0415

        raw = _decode_data_url(data_url)

        if len(raw) > _MAX_UPLOAD_BYTES:

            raise ValueError("imagem grande demais")

        img = Image.open(BytesIO(raw))

        img = img.convert("RGB")  # tira alpha/paleta; JPEG não tem alpha

        img.thumbnail((_MAX_SIDE, _MAX_SIDE))  # mantém proporção, só encolhe

        dest = self._photo_path(profile, key)

        dest.parent.mkdir(parents=True, exist_ok=True)

        img.save(dest, format="JPEG", quality=_JPEG_QUALITY, optimize=True)

        meta = self.load(profile)

        entry = self._entry(meta, key)

        entry["has_photo"] = True

        meta[key] = entry

        self._save(profile, meta)

    def photo_data_url(self, profile: str, key: str) -> str | None:
        """Bytes da foto como data URL (pro detalhe). None se não houver."""

        path = self._photo_path(profile, key)

        if not path.exists():

            return None

        try:

            b64 = base64.b64encode(path.read_bytes()).decode("ascii")

        except OSError:

            return None

        return f"data:image/jpeg;base64,{b64}"

    def delete_photo(self, profile: str, key: str) -> None:

        path = self._photo_path(profile, key)

        try:

            path.unlink(missing_ok=True)

        except OSError:

            pass

        meta = self.load(profile)

        entry = self._entry(meta, key)

        entry.pop("has_photo", None)

        self._prune(meta, key, entry)

        self._save(profile, meta)

    def _prune(self, meta: dict, key: str, entry: dict) -> None:
        """Tira a chave do JSON quando ela ficou sem título e sem foto."""

        if entry:

            meta[key] = entry

        else:

            meta.pop(key, None)


def _decode_data_url(data_url: str) -> bytes:

    s = (data_url or "").strip()

    if "," in s and s.lower().startswith("data:"):

        s = s.split(",", 1)[1]

    try:

        return base64.b64decode(s, validate=False)

    except (ValueError, TypeError) as e:

        raise ValueError("imagem inválida") from e
