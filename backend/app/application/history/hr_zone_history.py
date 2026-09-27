"""Histórico da régua de zonas de FC do atleta — a FC muda com a evolução
(repouso cai com o condicionamento, o teto muda com idade/forma), e a régua
acompanha ([[HrZoneResolver]]). Aqui fica o RASTRO dessas mudanças, uma
entrada por mudança real (não por ruído de 1 bpm), pra o coach perceber e
comentar a evolução ("tua FC de repouso caiu 66→60, as zonas mudaram").

Gravado a cada treino analisado (TrainingPipeline). Puro + persistência no
perfil (`hr_zones_history`)."""

from __future__ import annotations

from datetime import date, timedelta

from app.domain.value_objects.hr_zones import HrZones

# mudança menor que isto em todos os pisos é ruído (mediana de repouso oscila)
MIN_SHIFT_BPM = 2

# quanto tempo uma mudança conta como "recente" pro coach comentar
RECENT_DAYS = 21

# teto do rastro (o mais antigo sai)
MAX_ENTRIES = 24


class HrZoneHistory:

    @staticmethod
    def entry(zones: HrZones, day: date) -> dict:

        return {
            "date": day.isoformat(),
            "floors": list(zones.floors),
            "method": zones.method,
            "max_hr": zones.max_hr,
            "resting_hr": zones.resting_hr,
        }

    @staticmethod
    def changed(last: dict | None, zones: HrZones) -> bool:
        """Mudou de verdade? Sem entrada anterior = sim (linha de base).
        Troca de origem (relógio × calculada) = sim. Senão, algum piso andou
        ≥ MIN_SHIFT_BPM."""

        if not last or not last.get("floors"):

            return True

        def origin(method) -> str:

            return str(method or "").split(":")[0]

        if origin(last.get("method")) != origin(zones.method):

            return True

        return any(
            abs(int(old) - new) >= MIN_SHIFT_BPM
            for old, new in zip(last["floors"], zones.floors)
        )

    @staticmethod
    def append(history: list | None, zones: HrZones, day: date) -> list | None:
        """Novo histórico com a régua de hoje, ou None se nada mudou."""

        history = list(history or [])

        if not HrZoneHistory.changed(history[-1] if history else None, zones):

            return None

        history.append(HrZoneHistory.entry(zones, day))

        return history[-MAX_ENTRIES:]

    @staticmethod
    def record(profile: str, runner, zones: HrZones | None, day: date) -> None:
        """Grava a régua de hoje no perfil se mudou (e atualiza o `runner` em
        memória, pra a análise deste mesmo treino já enxergar). Best-effort."""

        if zones is None:

            return

        updated = HrZoneHistory.append(
            getattr(runner, "hr_zones_history", None), zones, day
        )

        if updated is None:

            return

        try:

            from app.infrastructure.persistence.runner_profile_repository import (
                RunnerProfileRepository,
            )

            RunnerProfileRepository().update_fields(
                profile, {"hr_zones_history": updated}
            )

            runner.hr_zones_history = updated

        except Exception as e:

            print(f"Zonas de FC: histórico não gravado p/ {profile}: {e}")

    @staticmethod
    def recent_change(
        history: list | None,
        today: date,
    ) -> tuple[dict, dict] | None:
        """(antes, agora) se a régua mudou nos últimos RECENT_DAYS dias — a
        linha de base (primeira entrada) não conta como mudança."""

        history = history or []

        if len(history) < 2:

            return None

        current = history[-1]

        try:

            when = date.fromisoformat(current["date"])

        except (KeyError, TypeError, ValueError):

            return None

        if today - when > timedelta(days=RECENT_DAYS):

            return None

        return history[-2], current

    @staticmethod
    def describe_change(before: dict, after: dict) -> str:
        """'em 20/09: Z2 era 140-152 bpm, agora 143-155 bpm (FC repouso 60→66)'."""

        def z2(entry: dict) -> str:

            floors = entry["floors"]

            return f"{floors[1]}-{floors[2] - 1}"

        when = date.fromisoformat(after["date"]).strftime("%d/%m")

        causes = []

        for key, label in (("resting_hr", "FC repouso"), ("max_hr", "FC máx")):

            old, new = before.get(key), after.get(key)

            if old and new and old != new:

                causes.append(f"{label} {old}→{new}")

        cause = f" ({', '.join(causes)})" if causes else ""

        return f"em {when}: Z2 era {z2(before)} bpm, agora {z2(after)} bpm{cause}"
