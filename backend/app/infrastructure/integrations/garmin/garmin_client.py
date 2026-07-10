"""Acesso autenticado ao Garmin Connect (rota não-oficial, via
garminconnect/garth). O login é feito UMA vez pelo próprio atleta (script
garmin_login.py) — a senha nunca passa pelo backend; aqui só carregamos o
token salvo e o renovamos sozinho enquanto valer.

Token por atleta em storage/garmin/{profile}/ (fora do git)."""

from pathlib import Path

from garminconnect import Garmin

_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "garmin"
)


class GarminNotConnected(Exception):
    """Sem token salvo pra este atleta — precisa rodar o login uma vez."""


class GarminClient:

    @staticmethod
    def token_dir(profile: str) -> Path:

        return _STORAGE / profile

    @staticmethod
    def is_connected(profile: str) -> bool:

        token_dir = GarminClient.token_dir(profile)

        return token_dir.exists() and any(token_dir.iterdir())

    @staticmethod
    def connect(profile: str) -> Garmin:
        """Cliente autenticado a partir do token salvo. Levanta
        GarminNotConnected se o atleta ainda não fez o login."""

        token_dir = GarminClient.token_dir(profile)

        if not GarminClient.is_connected(profile):

            raise GarminNotConnected(
                f"Garmin não conectado para '{profile}'. "
                f"Rode uma vez: python garmin_login.py {profile}"
            )

        garmin = Garmin()

        # resume a sessão a partir dos tokens salvos (sem senha)
        garmin.login(str(token_dir))

        return garmin
