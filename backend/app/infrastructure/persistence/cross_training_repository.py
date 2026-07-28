import json
from datetime import datetime
from pathlib import Path

from app.domain.entities.activity import Activity


class CrossTrainingRepository:
    """Contador de CARGA DO CORPO — atividades NÃO-corrida (musculação,
    natação, Hyrox, bike...) — storage/cross_training/{profile}.json.

    Existe SÓ pra a leitura do corpo (camada 2/3): esse estresse conta pro
    ACWR/veredito do corpo tanto quanto a corrida, porque a recuperação
    (HRV/sono) sente TUDO. Fonte ÚNICA = Garmin (o mesmo relógio que dá a
    saúde), então NÃO precisa deduplicar entre fontes como o arquivo de
    corrida faz. Guarda campos mínimos (o que a carga precisa: duração + FC);
    nunca alimenta leitura/plano/chat de CORRIDA. Ver
    [[project_analise_corpo_garmin]]."""

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "cross_training"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def load(self, profile: str) -> list[dict]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError):

            return []

    def load_activities(self, profile: str) -> list[Activity]:
        """Reconstrói como `Activity` mínimo (distância/GPS/streams como
        default) — basta pro TrainingLoadAnalyzer, que só olha duração + FC."""

        return [
            CrossTrainingRepository._from_record(record)
            for record in self.load(profile)
        ]

    def upsert_many(self, profile: str, activities: list[Activity]) -> None:
        """Grava por id (idempotente — a mesma atividade reaparece no poll e só
        atualiza, não duplica). Falhar aqui nunca derruba o poll de treino."""

        records = {record["id"]: record for record in self.load(profile)}

        for activity in activities:

            records[activity.id] = CrossTrainingRepository._to_record(activity)

        ordered = sorted(records.values(), key=lambda r: r["start_date"])

        file = self.storage / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump(ordered, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _from_record(record: dict) -> Activity:

        moving_time = int(record.get("moving_time", 0) or 0)

        return Activity(
            id=record["id"],
            name=record.get("sport", "Cross"),
            sport=record.get("sport", "Other"),
            start_date=datetime.fromisoformat(record["start_date"]),
            timezone="UTC",
            distance=0.0,
            moving_time=moving_time,
            elapsed_time=moving_time,
            average_speed=0.0,
            max_speed=0.0,
            average_heartrate=record.get("average_heartrate"),
            max_heartrate=None,
            elevation_gain=0.0,
            elevation_high=None,
            elevation_low=None,
            start_latitude=None,
            start_longitude=None,
            end_latitude=None,
            end_longitude=None,
            kudos=0,
            comments=0,
            suffer_score=None,
            raw={},
        )

    @staticmethod
    def _to_record(activity: Activity) -> dict:

        return {
            "id": activity.id,
            "sport": activity.sport,
            "start_date": activity.start_date.isoformat(),
            "moving_time": activity.moving_time,
            "average_heartrate": activity.average_heartrate,
        }
