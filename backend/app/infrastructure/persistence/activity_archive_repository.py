import json
from datetime import datetime
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

    def load_activities(
        self,
        profile: str,
    ) -> list[Activity]:
        """Reconstrói as atividades arquivadas como `Activity`, DEDUPLICADAS.
        O arquivo guarda campos reduzidos (o que basta pros agregados de
        histórico — volume, consistência, casamento por distância/data); o que
        não é persistido volta como default (raw vazio, sem GPS/streams).

        DEDUP: todo treino do Garmin sincroniza pro Strava, então a MESMA
        corrida entra no arquivo duas vezes (ids diferentes, ~mesma data/
        distância/tempo). Sem colapsar, a carga contava cada treino 2× (o ACWR
        é razão, então o veredito não muda, mas os números absolutos inflam) E
        as zonas de FC (só na cópia do Garmin) ficavam diluídas pela cópia
        Strava sem zonas — bloqueando a carga de Edwards. Colapsa preferindo a
        cópia com dado mais rico (zonas de FC)."""

        activities = [
            ActivityArchiveRepository._from_record(record)
            for record in self.load(profile)
        ]

        return ActivityArchiveRepository._dedup_runs(activities)

    @staticmethod
    def _dedup_runs(activities: list[Activity]) -> list[Activity]:
        """Colapsa o MESMO treino vindo de fontes diferentes (Garmin+Strava).
        Mesma tolerância apertada do LoadTrainingHistory (data + distância 0,5%
        + tempo 2%). Faz MERGE das duas cópias: mantém a com zonas de FC
        (Garmin) mas herda o que só a outra tem — em especial a temperatura
        (`air_temp_c`, que vem do Strava) pra normalização de calor."""

        kept: list[Activity] = []

        for activity in activities:

            dup = next(
                (
                    i
                    for i, other in enumerate(kept)
                    if ActivityArchiveRepository._same_run(activity, other)
                ),
                None,
            )

            if dup is None:

                kept.append(activity)

            else:

                kept[dup] = ActivityArchiveRepository._merge_dup(
                    kept[dup], activity
                )

        return kept

    @staticmethod
    def _merge_dup(existing: Activity, incoming: Activity) -> Activity:
        """Funde duas cópias do mesmo treino. Primário = o que tem zonas de FC
        (mais rico); herda do outro o que lhe falta (temperatura, zonas)."""

        primary, secondary = (
            (incoming, existing)
            if incoming.hr_zone_minutes and not existing.hr_zone_minutes
            else (existing, incoming)
        )

        if primary.air_temp_c is None and secondary.air_temp_c is not None:

            primary.air_temp_c = secondary.air_temp_c

        if primary.hr_zone_minutes is None and secondary.hr_zone_minutes:

            primary.hr_zone_minutes = secondary.hr_zone_minutes

        return primary

    @staticmethod
    def _same_run(a: Activity, b: Activity) -> bool:

        if a.id == b.id:

            return True

        if a.start_date.date() != b.start_date.date():

            return False

        biggest_dist = max(a.distance, b.distance, 1.0)

        if abs(a.distance - b.distance) > 0.005 * biggest_dist:

            return False

        biggest_time = max(a.moving_time, b.moving_time, 1)

        return abs(a.moving_time - b.moving_time) <= 0.02 * biggest_time

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
    def _from_record(
        record: dict,
    ) -> Activity:
        """Record reduzido -> Activity, preenchendo com default o que o
        arquivo não guarda (max_speed, GPS, raw, etc.). Suficiente pra
        história/agregados; NÃO serve pra enriquecer splits (o treino atual
        vem completo por outro caminho)."""

        moving_time = int(record.get("moving_time", 0) or 0)

        return Activity(
            id=record["id"],
            name=record.get("name", ""),
            sport=record.get("sport", "Run"),
            start_date=datetime.fromisoformat(record["start_date"]),
            timezone=record.get("timezone", "UTC"),
            distance=record.get("distance", 0.0),
            moving_time=moving_time,
            elapsed_time=int(record.get("elapsed_time", moving_time) or 0),
            average_speed=record.get("average_speed", 0.0),
            max_speed=record.get("max_speed", 0.0),
            average_heartrate=record.get("average_heartrate"),
            max_heartrate=record.get("max_heartrate"),
            elevation_gain=record.get("elevation_gain", 0.0),
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
            hr_zone_minutes=record.get("hr_zone_minutes"),
            air_temp_c=record.get("air_temp_c"),
        )

    @staticmethod
    def _to_record(
        activity: Activity,
    ) -> dict:

        record = {
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

        # zonas de FC (carga de Edwards) só quando calculadas — não polui os
        # registros antigos/sem stream com null à toa
        if activity.hr_zone_minutes is not None:

            record["hr_zone_minutes"] = activity.hr_zone_minutes

        # temperatura do treino (Strava) — pra normalização de calor do EF; só
        # quando o device gravou, pra não poluir registro antigo com null
        if activity.air_temp_c is not None:

            record["air_temp_c"] = activity.air_temp_c

        return record
