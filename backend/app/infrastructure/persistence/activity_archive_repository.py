import json
from pathlib import Path

from app.domain.entities.activity import Activity


class ActivityArchiveRepository:
    """Arquivo permanente das atividades do atleta —
    storage/activities/{profile}.json.

    O Strava só entrega as últimas N atividades; aqui tudo que já
    passou pelo sistema fica guardado, permitindo consultas de
    histórico de vida ("quanto corri em março?")."""

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "activities"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> list[dict]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        with open(
            file,
            encoding="utf-8",
        ) as f:

            return json.load(f)

    def upsert_many(
        self,
        profile: str,
        activities: list[Activity],
    ) -> None:

        records = {
            record["id"]: record
            for record in self.load(profile)
        }

        for activity in activities:

            records[activity.id] = ActivityArchiveRepository._to_record(
                activity,
            )

        ordered = sorted(
            records.values(),
            key=lambda record: record["start_date"],
        )

        file = self.storage / f"{profile}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                ordered,
                f,
                ensure_ascii=False,
                indent=2,
            )

    def remove(
        self,
        profile: str,
        activity_id: int,
    ) -> bool:
        """Remove uma atividade apagada no Strava. Sem isso o arquivo
        guardaria treinos que o atleta descartou (duplicados, registros
        errados), inflando km de vida e histórico. Retorna se removeu."""

        records = self.load(profile)

        remaining = [
            record for record in records
            if record["id"] != activity_id
        ]

        if len(remaining) == len(records):

            return False

        file = self.storage / f"{profile}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                remaining,
                f,
                ensure_ascii=False,
                indent=2,
            )

        return True

    def stats(
        self,
        profile: str,
    ) -> dict | None:
        """Agregados de vida para o contexto do coach."""

        records = self.load(profile)

        if not records:

            return None

        total_km = sum(
            record["distance"] for record in records
        ) / 1000

        longest_km = max(
            record["distance"] for record in records
        ) / 1000

        return {
            "total_runs": len(records),
            "total_km": round(total_km, 1),
            "first_date": records[0]["start_date"][:10],
            "longest_km": round(longest_km, 1),
        }

    @staticmethod
    def _to_record(
        activity: Activity,
    ) -> dict:

        return {
            "id": activity.id,
            "name": activity.name,
            "sport": activity.sport,
            "start_date": activity.start_date.isoformat(),
            "distance": activity.distance,
            "moving_time": activity.moving_time,
            "average_speed": activity.average_speed,
            "average_heartrate": activity.average_heartrate,
            "elevation_gain": activity.elevation_gain,
        }
