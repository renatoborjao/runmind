"""Override da ANÁLISE do Garmin pra um atleta. O PADRÃO é: quem tem Garmin
conectado já é analisado pelo Garmin (não precisa ligar nada). Este script é
só a válvula de escape: 'off' força a análise de volta ao Strava num toque
(se o mapeamento Garmin sair torto pra alguém); 'on' remove o override e volta
ao padrão.

Uso:  python garmin_analysis.py <profile> <on|off>
Ex.:  python garmin_analysis.py renato2 off   # forçar Strava
"""

import sys

from app.infrastructure.integrations.garmin.garmin_client import GarminClient


def main(profile: str, state: str) -> None:

    enabled = state.lower() in ("on", "1", "true", "sim")

    GarminClient.set_analysis(profile, enabled)

    if enabled:

        if not GarminClient.is_connected(profile):

            print(f"⚠️ Atenção: '{profile}' ainda NÃO está conectado ao "
                  f"Garmin (rode garmin_login.py). A análise só troca "
                  f"quando conectar.")

        print(f"✅ '{profile}' no PADRÃO: análise via GARMIN (override removido).")

    else:

        print(f"↩️ '{profile}' forçado pro STRAVA (override analysis_off ligado).")


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print("Uso: python garmin_analysis.py <profile> <on|off>")

        sys.exit(1)

    main(sys.argv[1], sys.argv[2])
