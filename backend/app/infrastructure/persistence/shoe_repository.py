"""Persiste o armário de tênis do atleta (storage/shoes/{profile}.json): os
pares, as regras de rodízio e as corridas já contadas. Km é número — soma
determinística, nunca texto na memória. Ver [[project_tracker_tenis]]."""

import json
from pathlib import Path

from app.domain.entities.shoe import Shoe, ShoeBook, ShoeRule


class ShoeRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "shoes"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> ShoeBook:

        file = self._file(profile)

        if not file.exists():

            return ShoeBook()

        try:

            with open(file, encoding="utf-8") as f:

                data = json.load(f)

        except (json.JSONDecodeError, OSError):

            return ShoeBook()

        return ShoeRepository._from_dict(data)

    def save(self, profile: str, book: ShoeBook) -> None:

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(
                ShoeRepository._to_dict(book), f, ensure_ascii=False, indent=2
            )

    def has_shoes(self, profile: str) -> bool:

        return bool(self.load(profile).active())

    # ---- (de)serialização ------------------------------------------------

    @staticmethod
    def _to_dict(book: ShoeBook) -> dict:

        return {
            "shoes": [
                {
                    "id": s.id,
                    "name": s.name,
                    "nickname": s.nickname,
                    "category": s.category,
                    "gear_id": s.gear_id,
                    "is_default": s.is_default,
                    "retired": s.retired,
                    "initial_km": s.initial_km,
                    "accumulated_km": s.accumulated_km,
                    "alert_threshold_km": s.alert_threshold_km,
                    "wear_alerted": s.wear_alerted,
                    "counted_ids": s.counted_ids,
                    "created_at": s.created_at,
                }
                for s in book.shoes
            ],
            "rules": [
                {"match": r.match, "shoe_id": r.shoe_id} for r in book.rules
            ],
            "counted_fingerprints": book.counted_fingerprints,
            "assignments": book.assignments,
            "last_activity_id": book.last_activity_id,
            "last_shoe_id": book.last_shoe_id,
            "last_km": book.last_km,
        }

    @staticmethod
    def _from_dict(data: dict) -> ShoeBook:

        shoes = [
            Shoe(
                id=s["id"],
                name=s["name"],
                nickname=s.get("nickname"),
                category=s.get("category"),
                gear_id=s.get("gear_id"),
                is_default=s.get("is_default", False),
                retired=s.get("retired", False),
                initial_km=s.get("initial_km", 0.0),
                accumulated_km=s.get("accumulated_km", 0.0),
                alert_threshold_km=s.get("alert_threshold_km", 700.0),
                wear_alerted=s.get("wear_alerted", False),
                counted_ids=s.get("counted_ids", []),
                created_at=s.get("created_at", ""),
            )
            for s in data.get("shoes", [])
        ]

        rules = [
            ShoeRule(match=r["match"], shoe_id=r["shoe_id"])
            for r in data.get("rules", [])
            if r.get("match") and r.get("shoe_id")
        ]

        return ShoeBook(
            shoes=shoes,
            rules=rules,
            counted_fingerprints=data.get("counted_fingerprints", []),
            assignments=data.get("assignments", {}),
            last_activity_id=data.get("last_activity_id"),
            last_shoe_id=data.get("last_shoe_id"),
            last_km=data.get("last_km", 0.0),
        )
