"""MAPA ATÉ A PROVA — o olhar pra FRENTE que faltava. O atleta via o bloco de 4 semanas
e a fase da semana; a "jornada" que existe é só retrospectiva ("olha o caminho que você
fez"). Aqui sai o caminho que VEM: quantas semanas faltam e como o ciclo costuma se
organizar até o dia da prova — construção, ritmo de prova, simulado, polimento.

NÃO é plano fixo e NÃO é guardado: é CALCULADO na hora, da data da prova e das mesmas
regras de periodização que o coach já usa (polimento proporcional à distância, UM
simulado antes do polimento — [[PHASE_EMPHASIS]] e [[race_calendar_directive]]). Sempre
rotulado "previsto": se o corpo pedir desvio (doença, sobrecarga, prova nova) o coach
desvia e o mapa se recalcula sozinho na semana seguinte ([[feedback_tudo_dinamico]]).
Sem números de volume — só fases e marcos.

Acompanha a prova-FOCO (a próxima principal; sem principal, a mais próxima). Com VÁRIAS
provas o caminho passa por elas: uma PREPARATÓRIA (B) antes da principal vira etapa do
mapa — mini-polimento na semana dela e uma semana de recuperação depois, como o coach
trata (calendário de provas: "marco no caminho, só mini-polimento, recupere e retome") —
desde que sobrem ~3 semanas até a principal; menos que isso, ou prova de TREINO (C), ela
entra só como marco. Provas depois da principal também ficam como marco. Sem prova com
data → sem mapa. Puro/determinístico, sem IA."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# o mapa só faz sentido com a prova no horizonte
MAX_WEEKS = 36

# construção: no máximo estas semanas antes do ritmo de prova (o resto é base)
_BUILD_MAX_WEEKS = 6

# semanas entre uma prova preparatória e a principal pra ela virar etapa do caminho
# (menos que isso: "a de menor papel vira treino")
_MIN_GAP_WEEKS = 3

BASE = "base"
BUILD = "construcao"
SPECIFIC = "ritmo_de_prova"
SIMULATED = "simulado"
TAPER = "polimento"
MINI = "mini_polimento"
RECOVERY = "recuperacao"

LABELS = {
    BASE: "Base",
    BUILD: "Construção",
    SPECIFIC: "Ritmo de prova",
    SIMULATED: "Simulado",
    TAPER: "Polimento e prova",
    MINI: "Mini-polimento e prova",
    RECOVERY: "Recuperação e retomada",
}

# como cada fase aparece na linha corrida do plano de domingo
_SHORT = {
    BASE: "base",
    BUILD: "construção",
    SPECIFIC: "ritmo de prova",
    SIMULATED: "simulado",
    TAPER: "polimento",
    MINI: "mini-polimento",
    RECOVERY: "recuperação",
}

_ROLE_WORD = {"A": "principal", "B": "preparatória", "C": "de treino"}


def taper_weeks(distance_km: float | None) -> int:
    """Semanas de polimento pela DISTÂNCIA (a mesma ideia do calendário de provas:
    10 km ~7–10 dias, meia ~10–14, maratona ~2–3 semanas). Sem distância: curto."""

    d = distance_km or 10.0

    if d <= 16:

        return 1

    if d <= 25:

        return 2

    return 3


def specific_weeks(distance_km: float | None) -> int:
    """Semanas de ritmo de prova (afiação específica) antes do simulado."""

    d = distance_km or 10.0

    if d <= 16:

        return 2

    if d <= 25:

        return 3

    return 4


@dataclass(slots=True)
class MapSegment:

    key: str
    label: str
    start: date
    end: date
    weeks: int
    current: bool = False
    race_label: str | None = None    # a prova preparatória (só no mini-polimento)


@dataclass(slots=True)
class RaceMap:

    race_name: str
    distance_km: float | None
    race_date: date
    weeks_left: int                  # inclui a semana da prova e a semana atual
    segments: list[MapSegment] = field(default_factory=list)
    markers: list[dict] = field(default_factory=list)
    # provas preparatórias que viraram etapa do caminho (label, data, semanas até ela)
    waypoints: list[dict] = field(default_factory=list)

    @property
    def current(self) -> MapSegment | None:

        return next((s for s in self.segments if s.current), None)


def _monday(day: date) -> date:

    return day - timedelta(days=day.weekday())


def _distance_label(distance_km: float | None, name: str | None) -> str:

    if distance_km:

        if abs(distance_km - 21.0975) < 0.2:

            return "meia maratona"

        if abs(distance_km - 42.195) < 0.3:

            return "maratona"

        whole = abs(distance_km - round(distance_km)) < 0.05

        text = f"{distance_km:.0f}" if whole else f"{distance_km:.1f}"

        return f"{text} km".replace(".", ",")

    return name or "prova"


def _countdown(weeks: int, target: str, when: str, *, verb: bool = True) -> str:
    """"Faltam 8 semanas pra 15 km (20/12)" — `verb=False` pra segunda prova da frase
    ("e 23 pra meia maratona (04/04)")."""

    if verb:

        head = "Falta 1 semana" if weeks == 1 else f"Faltam {weeks} semanas"

    else:

        head = str(weeks)

    return f"{head} pra {target} ({when})"


class RaceMapBuilder:

    @staticmethod
    def build(
        race_date: date,
        distance_km: float | None,
        week_start: date,
        *,
        name: str | None = None,
        markers: list[dict] | None = None,
        waypoints: list[dict] | None = None,
    ) -> RaceMap | None:
        """O mapa visto da semana que começa em `week_start`. None se a prova já
        passou ou está longe demais pra ser útil. `waypoints`: provas preparatórias
        antes da principal ({"date": date, "label": str}); as que não deixam ~3
        semanas até a principal viram marcos."""

        week_start = _monday(week_start)

        race_week = _monday(race_date)

        if race_week < week_start:

            return None

        weeks_left = (race_week - week_start).days // 7 + 1

        if weeks_left > MAX_WEEKS:

            return None

        keys = [
            key
            for key, count in RaceMapBuilder._sizes(weeks_left, distance_km)
            for _ in range(count)
        ]

        labels: list[str | None] = [None] * weeks_left

        ends: dict[int, date] = {weeks_left - 1: race_date}

        extra_markers = list(markers or [])

        used: list[dict] = []

        for wp in sorted(waypoints or [], key=lambda w: w["date"]):

            idx = (_monday(wp["date"]) - week_start).days // 7

            if idx < 0:

                continue

            if weeks_left - 1 - idx < _MIN_GAP_WEEKS:

                extra_markers.append(
                    {
                        "label": wp["label"],
                        "date_iso": wp["date"].isoformat(),
                        "role": "preparatória",
                        "when": "before",
                        "note": "perto da principal: entra como treino, sem polimento",
                    }
                )

                continue

            keys[idx] = MINI

            labels[idx] = wp["label"]

            ends[idx] = wp["date"]

            if idx + 1 < weeks_left:

                keys[idx + 1] = RECOVERY

            used.append(
                {
                    "label": wp["label"],
                    "date_iso": wp["date"].isoformat(),
                    "weeks_left": idx + 1,
                }
            )

        segments: list[MapSegment] = []

        i = 0

        while i < weeks_left:

            j = i

            while (
                j + 1 < weeks_left
                and keys[j + 1] == keys[i]
                and labels[j + 1] == labels[i]
                and keys[i] != MINI
            ):

                j += 1

            start = week_start + timedelta(days=7 * i)

            end = week_start + timedelta(days=7 * j + 6)

            if j in ends:

                end = min(end, ends[j])

            label = (
                f"{labels[i]}: mini-polimento e prova"
                if keys[i] == MINI
                else LABELS[keys[i]]
            )

            segments.append(
                MapSegment(
                    keys[i], label, start, end, j - i + 1,
                    race_label=labels[i] if keys[i] == MINI else None,
                )
            )

            i = j + 1

        if segments:

            segments[0].current = True

        return RaceMap(
            race_name=name or "",
            distance_km=distance_km,
            race_date=race_date,
            weeks_left=weeks_left,
            segments=segments,
            markers=extra_markers,
            waypoints=used,
        )

    @staticmethod
    def _sizes(weeks_left: int, distance_km: float | None) -> list[tuple[str, int]]:
        """As fases, da primeira semana até a da prova. Distribuídas DE TRÁS PRA
        FRENTE a partir da prova: com pouco tempo sobra só o fim do ciclo."""

        plan: list[tuple[str, int]] = []

        remaining = weeks_left

        for key, size in (
            (TAPER, taper_weeks(distance_km)),
            (SIMULATED, 1),
            (SPECIFIC, specific_weeks(distance_km)),
            (BUILD, _BUILD_MAX_WEEKS),
        ):

            take = min(size, remaining)

            if take:

                plan.append((key, take))

                remaining -= take

        if remaining:

            plan.append((BASE, remaining))

        plan.reverse()

        return plan

    # ------------------------------------------------------------------

    @staticmethod
    def for_profile(profile: str | None, week_start: date) -> RaceMap | None:
        """O mapa do atleta pra semana que começa em `week_start`: prova-foco e
        demais provas vêm da lista de provas do app. Best-effort — qualquer falha =
        None (o plano sai igual, sem o mapa)."""

        if not profile:

            return None

        try:

            from app.application.coach.planning.race_calendar_directive import (
                future_races,
            )
            from app.application.coach.planning.race_cycle import RaceCycle

            ahead = future_races(RaceCycle.races(profile), _monday(week_start))

            if not ahead:

                return None

            principal = [r for r in ahead if r.get("priority_effective") == "A"]

            focus = principal[0] if principal else ahead[0]

            waypoints, markers = [], []

            for race in ahead:

                if race is focus:

                    continue

                before = race["date"] < focus["date"]

                if before and race.get("priority_effective") == "B":

                    waypoints.append(
                        {
                            "date": date.fromisoformat(race["date"]),
                            "label": _distance_label(
                                race.get("distance_km"), race.get("name")
                            ),
                        }
                    )

                else:

                    markers.append(RaceMapBuilder._marker(race, before))

            return RaceMapBuilder.build(
                date.fromisoformat(focus["date"]),
                focus.get("distance_km"),
                week_start,
                name=focus.get("name"),
                markers=markers,
                waypoints=waypoints,
            )

        except Exception as e:  # noqa: BLE001

            print(f"Mapa até a prova falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    def _marker(race: dict, before: bool) -> dict:

        role = race.get("priority_effective")

        note = None

        if not before:

            note = "depois da principal"

        elif role == "C":

            note = "entra como treino, sem polimento"

        return {
            "label": _distance_label(race.get("distance_km"), race.get("name")),
            "date_iso": race["date"],
            "role": _ROLE_WORD.get(role),
            "when": "before" if before else "after",
            "note": note,
        }

    # ------------------------------------------------------------------

    @staticmethod
    def _head(race_map: RaceMap) -> str:
        """"Faltam 8 semanas pra 15 km (20/12)" — com provas preparatórias no
        caminho, todas na mesma frase, da mais próxima à principal."""

        target = _distance_label(race_map.distance_km, race_map.race_name)

        parts = [
            (w["weeks_left"], w["label"], date.fromisoformat(w["date_iso"]))
            for w in race_map.waypoints
        ]

        parts.append((race_map.weeks_left, target, race_map.race_date))

        return " e ".join(
            _countdown(weeks, label, day.strftime("%d/%m"), verb=i == 0)
            for i, (weeks, label, day) in enumerate(parts)
        )

    @staticmethod
    def line(race_map: RaceMap | None) -> str:
        """UMA linha pro plano de domingo (e pro "qual meu plano?"). Vazia sem mapa."""

        if race_map is None or not race_map.segments:

            return ""

        when = race_map.race_date.strftime("%d/%m")

        current = race_map.current

        if race_map.weeks_left == 1:

            target = _distance_label(race_map.distance_km, race_map.race_name)

            return (
                f"🗺️ Semana da prova: {target} em {when} — polimento e confiança no "
                "que você construiu. (previsto)"
            )

        steps, seen = [], set()

        for seg in race_map.segments:

            # a recuperação depois de uma preparatória e a base que ela interrompeu
            # não viram passo — o que o atleta precisa ver é o caminho
            if seg.key == RECOVERY or (seg.key in seen and seg.key != MINI):

                continue

            seen.add(seg.key)

            text = _SHORT[seg.key]

            when_text = "agora" if seg is current else seg.start.strftime("%d/%m")

            steps.append(f"{text} {when_text}")

        # caminho longo: o que o atleta precisa enxergar é o próximo passo e o fim
        if len(steps) > 4:

            steps = [steps[0], steps[1], *steps[-2:]]

        later = [m for m in race_map.markers if m.get("when") == "after"]

        tail = (
            f" Depois: {later[0]['label']} em "
            f"{date.fromisoformat(later[0]['date_iso']).strftime('%d/%m')}."
            if later
            else ""
        )

        return (
            f"🗺️ {RaceMapBuilder._head(race_map)}: {' → '.join(steps)}.{tail} "
            "(previsto — se ajusta ao seu corpo)"
        )

    @staticmethod
    def payload(race_map: RaceMap | None) -> dict | None:
        """O mapa pro app (aba Treino): fases com datas, marcos e o aviso de
        previsto. None sem mapa."""

        if race_map is None or not race_map.segments:

            return None

        return {
            "race_name": race_map.race_name,
            "target": _distance_label(race_map.distance_km, race_map.race_name),
            "race_date": race_map.race_date.isoformat(),
            "weeks_left": race_map.weeks_left,
            "current_key": race_map.current.key if race_map.current else None,
            "segments": [
                {
                    "key": s.key,
                    "label": s.label,
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "weeks": s.weeks,
                    "current": s.current,
                    "race_label": s.race_label,
                }
                for s in race_map.segments
            ],
            "markers": race_map.markers,
            "note": "Previsto — o coach ajusta se o seu corpo pedir.",
        }
