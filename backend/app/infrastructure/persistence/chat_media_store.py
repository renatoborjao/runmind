"""Fotos que o atleta manda pro coach (app ou Telegram). Ficam guardadas pra
aparecer na conversa do app — a mensagem guarda só o id. Normaliza tudo pra
JPEG (orientação da câmera corrigida, lado maior limitado): foto do celular vem
enorme e às vezes deitada.

storage/chat_media/{profile}/{id}.jpg
"""

from __future__ import annotations

import base64
import io
import re
import uuid
from pathlib import Path

from PIL import Image, ImageOps

_MAX_SIDE = 1600

_JPEG_QUALITY = 82

_ID = re.compile(r"^[0-9a-f]{32}$")


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    """`data:<mime>;base64,<...>` (ou base64 cru) -> (bytes, mimetype).
    Levanta ValueError se não decodifica."""

    s = (data_url or "").strip()

    mimetype = ""

    if s.lower().startswith("data:") and "," in s:

        header, s = s.split(",", 1)

        mimetype = header[5:].split(";", 1)[0].strip().lower()

    try:

        raw = base64.b64decode(s, validate=False)

    except (ValueError, TypeError) as e:

        raise ValueError("arquivo inválido") from e

    if not raw:

        raise ValueError("arquivo vazio")

    return raw, mimetype


class ChatMediaStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "chat_media"
        )

    def save_image(self, profile: str, raw: bytes) -> tuple[str, bytes]:
        """Normaliza e grava a foto. Devolve (id, bytes JPEG gravados) — os
        bytes normalizados são os que a IA lê (menores, orientação certa).
        Levanta ValueError se não é uma imagem."""

        try:

            img = Image.open(io.BytesIO(raw))

            img = ImageOps.exif_transpose(img)

            img = img.convert("RGB")

        except Exception as e:

            raise ValueError("imagem inválida") from e

        img.thumbnail((_MAX_SIDE, _MAX_SIDE))

        out = io.BytesIO()

        img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)

        data = out.getvalue()

        media_id = uuid.uuid4().hex

        folder = self.storage / profile

        folder.mkdir(parents=True, exist_ok=True)

        (folder / f"{media_id}.jpg").write_bytes(data)

        return media_id, data

    def path(self, profile: str, media_id: str) -> Path | None:
        """Arquivo da foto do PRÓPRIO atleta; None se id inválido/inexistente
        (id é validado: nada de path traversal)."""

        if not _ID.match(media_id or ""):

            return None

        file = self.storage / profile / f"{media_id}.jpg"

        return file if file.exists() else None
