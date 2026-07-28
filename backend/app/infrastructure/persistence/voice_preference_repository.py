"""Preferência de VOZ do atleta: quer receber os áudios proativos do coach
(bom dia, dia da prova, recorde) ou só texto? Fica FORA do perfil rígido —
o atleta liga/desliga conversando ("prefiro sem áudio", "pode mandar voz"),
fiel ao 'tudo é dinâmico'. Padrão: ligado (a voz é o ponto da feature). O
espelho (responder em voz quem falou em voz) NÃO passa por aqui — quem falou
por voz já consentiu. Ver [[project_ideias_produto]]."""

import json
from pathlib import Path

_FILE = (
    Path(__file__).resolve().parents[3]
    / "storage"
    / "voice_preference.json"
)


class VoicePreferenceRepository:

    @staticmethod
    def _load() -> dict:

        if not _FILE.exists():

            return {}

        try:

            return json.loads(_FILE.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):

            return {}

    @staticmethod
    def wants_audio(profile: str) -> bool:
        """True (padrão) até o atleta pedir só texto."""

        return VoicePreferenceRepository._load().get(profile, True)

    @staticmethod
    def set(profile: str, wants: bool) -> None:

        _FILE.parent.mkdir(parents=True, exist_ok=True)

        data = VoicePreferenceRepository._load()

        data[profile] = wants

        _FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
