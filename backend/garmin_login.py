"""Login único no Garmin Connect por atleta. A senha é digitada por VOCÊ
aqui no terminal (getpass, não aparece na tela) e NÃO é salva — só o token
gerado fica guardado em storage/garmin/{profile}/, e é ele que o RunMind usa
depois pra empurrar os treinos pro relógio.

Uso:  python garmin_login.py <profile>
Ex.:  python garmin_login.py renato2
"""

import getpass
import sys

from garminconnect import Garmin

from app.infrastructure.integrations.garmin.garmin_client import GarminClient


def main(profile: str) -> None:

    token_dir = GarminClient.token_dir(profile)

    token_dir.mkdir(parents=True, exist_ok=True)

    print(f"Login do Garmin para o atleta '{profile}'.")

    email = input("E-mail do Garmin Connect: ").strip()

    password = getpass.getpass("Senha (não aparece ao digitar): ")

    def prompt_mfa() -> str:

        return input("Código de verificação (MFA), se pedido: ").strip()

    garmin = Garmin(email, password, prompt_mfa=prompt_mfa)

    garmin.login()

    # salva os tokens (oauth1/oauth2) — a senha não é gravada
    garmin.garth.dump(str(token_dir))

    print()
    print(f"✅ Conectado! Token salvo em {token_dir}")

    # marca o histórico atual como 'já visto' — só treinos DEPOIS do login
    # geram análise (nada de feedback retroativo do histórico antigo)
    from app.application.garmin.garmin_activity_poller import (
        GarminActivityPoller,
    )

    GarminActivityPoller.seed_history(profile)

    print("Histórico marcado. A partir de agora o RunMind empurra treinos")
    print("pro seu Garmin e analisa pelos dados dele.")


if __name__ == "__main__":

    if len(sys.argv) != 2:

        print("Uso: python garmin_login.py <profile>")

        sys.exit(1)

    main(sys.argv[1])
