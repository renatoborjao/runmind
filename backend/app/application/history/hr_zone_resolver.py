"""Resolve as zonas de FC de UM atleta — fonte única de [[HrZones]].

Ordem (da mais pra menos fiel):
  1. zonas do RELÓGIO (Garmin), gravadas no perfil a cada treino — é o que o
     atleta vê no Garmin Connect, então o Ritmind fala a mesma língua;
  2. reserva de FC (Karvonen, padrão do Garmin) com FC máx = maior entre a
     observada em corrida e Tanaka, e FC de repouso = mediana da série de
     saúde do Garmin (ou do perfil);
  3. %FCmáx, quando não há FC de repouso;
  4. None sem idade nem FC máx observada (aí ninguém rotula zona)."""

from __future__ import annotations

import statistics

from app.domain.value_objects.hr_zones import HrZones
from app.domain.value_objects.sports import is_run_sport

# FC máx plausível de corrida (descarta sensor travado/erro de leitura)
_MAX_HR_FLOOR = 150
_MAX_HR_CEILING = 215

# FC de repouso plausível
_REST_FLOOR = 30
_REST_CEILING = 100

# janela da mediana de FC de repouso (dias mais recentes da série)
_REST_WINDOW = 30


class HrZoneResolver:

    @staticmethod
    def resolve(
        runner,
        activities: list | None = None,
        resting_hr: int | None = None,
    ) -> HrZones | None:

        configured = HrZones.from_dict(getattr(runner, "hr_zones", None))

        if configured is not None:

            return configured

        max_hr = HrZoneResolver.max_hr(
            getattr(runner, "age", None), activities or []
        )

        if max_hr is None:

            return None

        if resting_hr and _REST_FLOOR <= resting_hr <= _REST_CEILING < max_hr:

            return HrZones.from_hrr(max_hr, int(resting_hr))

        return HrZones.from_max(max_hr)

    @staticmethod
    def for_profile(
        profile: str,
        runner,
        activities: list | None = None,
    ) -> HrZones | None:
        """resolve() carregando a FC de repouso da série de saúde do Garmin.
        Best-effort: falha de leitura cai no %FCmáx."""

        resting = None

        if HrZones.from_dict(getattr(runner, "hr_zones", None)) is None:

            try:

                from app.infrastructure.persistence.garmin_health_repository import (
                    GarminHealthRepository,
                )

                resting = HrZoneResolver.median_resting(
                    GarminHealthRepository().load(profile)
                )

            except Exception as e:

                print(f"Zonas de FC: repouso indisponível p/ {profile}: {e}")

        return HrZoneResolver.resolve(runner, activities, resting)

    @staticmethod
    def max_hr(age, activities: list) -> int | None:
        """FC máx: MAIOR entre a observada em corrida (piso real do teto) e
        Tanaka (208 − 0,7·idade), que cobre quem nunca foi ao máximo."""

        tanaka = round(208 - 0.7 * age) if age and age > 0 else None

        peaks = [
            a.max_heartrate
            for a in activities
            if is_run_sport(getattr(a, "sport", "") or "")
            and getattr(a, "max_heartrate", None)
            and _MAX_HR_FLOOR <= a.max_heartrate <= _MAX_HR_CEILING
        ]

        observed = round(max(peaks)) if peaks else None

        candidates = [v for v in (tanaka, observed) if v is not None]

        return max(candidates) if candidates else None

    @staticmethod
    def median_resting(series: list) -> int | None:

        values = [
            h.resting_hr
            for h in (series or [])[-_REST_WINDOW:]
            if getattr(h, "resting_hr", None)
        ]

        return round(statistics.median(values)) if values else None
