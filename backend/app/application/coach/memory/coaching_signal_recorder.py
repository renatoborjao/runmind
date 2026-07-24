import json
from pathlib import Path

from app.core.clock import now_local

# no máximo isso de sinais crus acumulados por atleta — a destilação semanal
# limpa tudo, então em uso normal fica bem abaixo; o teto só evita crescimento
# ilimitado se um domingo de destilação falhar por semanas
_MAX_SIGNALS = 50


class CoachingSignalRecorder:
    """Guarda sinais CRUS da semana (correções que o atleta aceitou etc.) em
    storage/learning_signals/{profile}.json. Acumula durante a semana e é
    ZERADO pela destilação de domingo, que os transforma em aprendizado
    durável. É a Fonte A do cérebro coach — o sinal de mais alta qualidade,
    porque é o atleta corrigindo o coach de propósito."""

    @staticmethod
    def _dir() -> Path:

        path = (
            Path(__file__)
            .resolve()
            .parents[4]
            / "storage"
            / "learning_signals"
        )

        path.mkdir(parents=True, exist_ok=True)

        return path

    @staticmethod
    def record(
        profile: str,
        kind: str,
        detail: str,
    ) -> None:
        """Anexa um sinal. Best-effort por natureza: quem chama envolve em
        try/except pra que registrar nunca derrube o fluxo do atleta."""

        signals = CoachingSignalRecorder.load(profile)

        signals.append(
            {
                "kind": kind,
                "detail": detail,
                "at": now_local().isoformat(),
            }
        )

        CoachingSignalRecorder._save(profile, signals[-_MAX_SIGNALS:])

    @staticmethod
    def load(
        profile: str,
    ) -> list[dict]:

        file = CoachingSignalRecorder._dir() / f"{profile}.json"

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                data = json.load(f)

        except (json.JSONDecodeError, OSError):

            return []

        return data if isinstance(data, list) else []

    @staticmethod
    def clear(
        profile: str,
    ) -> None:

        file = CoachingSignalRecorder._dir() / f"{profile}.json"

        if file.exists():

            file.unlink()

    @staticmethod
    def _save(
        profile: str,
        signals: list[dict],
    ) -> None:

        file = CoachingSignalRecorder._dir() / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump(signals, f, ensure_ascii=False, indent=2)
