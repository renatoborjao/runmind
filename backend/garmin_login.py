"""Login único no Garmin Connect por atleta. A senha é digitada por VOCÊ
aqui no terminal (getpass, não aparece na tela) e NÃO é salva — só o token
gerado fica guardado em storage/garmin/{profile}/, e é ele que o Ritmind usa
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

    # login(tokenstore) autentica E salva o token no diretório — a senha
    # não é gravada, só os tokens oauth
    garmin.login(str(token_dir))

    print()
    print(f"✅ Conectado! Token salvo em {token_dir}")

    # marca o histórico atual como 'já visto' — só treinos DEPOIS do login
    # geram análise (nada de feedback retroativo do histórico antigo)
    from app.application.garmin.garmin_activity_poller import (
        GarminActivityPoller,
    )

    GarminActivityPoller.seed_history(profile)

    print("Histórico marcado. A partir de agora o Ritmind empurra treinos")
    print("pro seu Garmin e analisa pelos dados dele.")

    # backfill do CORPO (sono/HRV/prontidão/VO₂máx) na hora — senão o app do
    # atleta nasce sem anel de prontidão e sem leitura de recuperação até o
    # poll horário acumular dia a dia. seed_history é paced e para sozinho
    # após alguns dias vazios; best-effort (o token já está salvo, não pode
    # derrubar o login se a saúde falhar).
    from app.application.garmin.garmin_health_poller import GarminHealthPoller

    try:

        print("Puxando histórico de saúde (sono/HRV/prontidão)...", flush=True)

        pulled = GarminHealthPoller.seed_history(profile)

        print(f"Saúde: {pulled} dias gravados — o app já mostra teu corpo.")

    except Exception as exc:  # noqa: BLE001 — login não pode cair por causa disso

        print(f"⚠️ Saúde não semeada agora ({exc}); o poll horário preenche.")


if __name__ == "__main__":

    if len(sys.argv) != 2:

        print("Uso: python garmin_login.py <profile>")

        sys.exit(1)

    main(sys.argv[1])
