"""Liga/desliga a ANÁLISE via Garmin pra um atleta (separado de estar
conectado). Use 'off' pra voltar a análise pro Strava num toque se algo
sair torto durante a verificação do mapeamento.

Uso:  python garmin_analysis.py <profile> <on|off>
Ex.:  python garmin_analysis.py renato2 on
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

        print(f"✅ Análise via GARMIN LIGADA para '{profile}'.")

    else:

        print(f"↩️ Análise de '{profile}' de volta ao STRAVA (Garmin off).")


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print("Uso: python garmin_analysis.py <profile> <on|off>")

        sys.exit(1)

    main(sys.argv[1], sys.argv[2])
