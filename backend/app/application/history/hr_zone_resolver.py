"""Resolve as zonas de FC de UM atleta — fonte única de [[HrZones]].

A régua é VIVA: a FC do atleta muda com a evolução (repouso cai com o
condicionamento, o teto muda com idade/forma), então nada aqui é fixo.

Ordem (da mais pra menos fiel):
  1. zonas do RELÓGIO (Garmin), regravadas a cada treino novo — é o que o
     atleta vê no Garmin Connect, então o Ritmind fala a mesma língua. Só
     valem se ESTÃO EM DIA: recentes (≤60 dias) e com a FC máx do relógio não
     ultrapassada nas corridas recentes (senão a config ficou pra trás);
  2. reserva de FC (Karvonen, padrão do Garmin) com FC máx = maior entre o
     pico de corrida do ÚLTIMO ANO e Tanaka, e FC de repouso = mediana dos
     últimos 30 dias da saúde do Garmin — as duas acompanham a evolução;
  3. %FCmáx, quando não há FC de repouso;
  4. None sem idade nem FC máx observada (aí ninguém rotula zona).
Mudanças de régua ficam no histórico do perfil ([[HrZoneHistory]])."""

from __future__ import annotations

import statistics
from datetime import date, timedelta

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

# pico de FC que conta como teto: só o último ano (o teto muda com a idade e a
# forma — um pico de 3 anos atrás não descreve o atleta de hoje)
_PEAK_WINDOW_DAYS = 365

# zonas do relógio sem treino novo há mais que isto = atleta largou o Garmin
_WATCH_STALE_DAYS = 60

# pico recente acima da FC máx do relógio (+folga de sensor) = config velha
_WATCH_PEAK_WINDOW_DAYS = 180
_WATCH_PEAK_TOLERANCE = 2


class HrZoneResolver:

    @staticmethod
    def resolve(
        runner,
        activities: list | None = None,
        resting_hr: int | None = None,
        today: date | None = None,
    ) -> HrZones | None:

        activities = activities or []

        today = today or HrZoneResolver._today()

        watch = HrZoneResolver._watch_zones(runner, activities, today)

        if watch is not None:

            return watch

        max_hr = HrZoneResolver.max_hr(
            getattr(runner, "age", None), activities, today
        )

        if max_hr is None:

            return None

        if resting_hr and _REST_FLOOR <= resting_hr <= _REST_CEILING < max_hr:

            return HrZones.from_hrr(max_hr, int(resting_hr))

        return HrZones.from_max(max_hr)

    @staticmethod
    def _watch_zones(runner, activities: list, today: date) -> HrZones | None:
        """Zonas do relógio, SE em dia. Relógio largado (sem treino novo há
        60+ dias) ou FC máx do relógio já ultrapassada em corrida recente =
        config que não descreve mais o atleta — cai na régua calculada."""

        stored = getattr(runner, "hr_zones", None) or {}

        zones = HrZones.from_dict(stored)

        if zones is None:

            return None

        as_of = stored.get("as_of")

        if as_of:

            try:

                if (today - date.fromisoformat(as_of)).days > _WATCH_STALE_DAYS:

                    return None

            except ValueError:

                return None

        if zones.max_hr:

            peak = HrZoneResolver._peak(
                activities, today, _WATCH_PEAK_WINDOW_DAYS
            )

            if peak is not None and peak > zones.max_hr + _WATCH_PEAK_TOLERANCE:

                return None

        return zones

    @staticmethod
    def for_profile(
        profile: str,
        runner,
        activities: list | None = None,
    ) -> HrZones | None:
        """resolve() carregando a FC de repouso ATUAL (últimos 30 dias da
        saúde do Garmin) — sempre, porque as zonas do relógio podem estar
        vencidas e aí a régua calculada precisa dela. Best-effort: falha de
        leitura cai no %FCmáx."""

        resting = None

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
    def max_hr(age, activities: list, today: date | None = None) -> int | None:
        """FC máx: MAIOR entre o pico de corrida do último ano (piso real do
        teto atual) e Tanaka (208 − 0,7·idade), que cobre quem nunca foi ao
        máximo."""

        tanaka = round(208 - 0.7 * age) if age and age > 0 else None

        observed = HrZoneResolver._peak(
            activities, today or HrZoneResolver._today(), _PEAK_WINDOW_DAYS
        )

        candidates = [v for v in (tanaka, observed) if v is not None]

        return max(candidates) if candidates else None

    @staticmethod
    def _peak(activities: list, today: date, days: int) -> int | None:
        """Maior FC máx plausível de corrida nos últimos `days` dias."""

        since = today - timedelta(days=days)

        peaks = [
            a.max_heartrate
            for a in activities
            if is_run_sport(getattr(a, "sport", "") or "")
            and getattr(a, "max_heartrate", None)
            and _MAX_HR_FLOOR <= a.max_heartrate <= _MAX_HR_CEILING
            and getattr(a, "start_date", None) is not None
            and a.start_date.date() >= since
        ]

        return round(max(peaks)) if peaks else None

    @staticmethod
    def _today() -> date:

        from app.core.clock import today_local

        return today_local()

    @staticmethod
    def median_resting(series: list) -> int | None:

        values = [
            h.resting_hr
            for h in (series or [])[-_REST_WINDOW:]
            if getattr(h, "resting_hr", None)
        ]

        return round(statistics.median(values)) if values else None
