"""Despeja o JSON REAL de uma atividade do Garmin (resumo + splits +
typed_splits + amostra dos details) num arquivo, pra conferir os nomes de
campo exatos e finalizar o mapeamento da análise.

Uso:  python garmin_dump.py <profile> [activity_id]
Sem activity_id, pega a última atividade.
"""

import json
import sys

from app.infrastructure.integrations.garmin.garmin_client import GarminClient


def main(profile: str, activity_id: int | None) -> None:

    garmin = GarminClient.connect(profile)

    if activity_id is None:

        last = garmin.get_activities(0, 1)

        if not last:

            print("Nenhuma atividade encontrada no Garmin.")

            return

        activity_id = last[0].get("activityId")

        print(f"Última atividade: {activity_id}")

    out: dict = {}

    def grab(label, fn):

        try:

            out[label] = fn()

        except Exception as e:

            out[label] = {"__erro__": str(e)}

    grab("summary", lambda: garmin.get_activity(activity_id))
    grab("splits", lambda: garmin.get_activity_splits(activity_id))
    grab("typed_splits", lambda: garmin.get_activity_typed_splits(activity_id))

    # details é gigante — guarda só descriptors + 2 linhas de amostra
    try:

        det = garmin.get_activity_details(activity_id)

        out["details_sample"] = {
            "metricDescriptors": det.get("metricDescriptors"),
            "activityDetailMetrics_head": (
                det.get("activityDetailMetrics") or []
            )[:2],
        }

    except Exception as e:

        out["details_sample"] = {"__erro__": str(e)}

    path = f"storage/garmin/dump_{activity_id}.json"

    with open(path, "w", encoding="utf-8") as f:

        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(f"Dump salvo em {path} — me manda esse arquivo.")


if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("Uso: python garmin_dump.py <profile> [activity_id]")

        sys.exit(1)

    aid = int(sys.argv[2]) if len(sys.argv) > 2 else None

    main(sys.argv[1], aid)
