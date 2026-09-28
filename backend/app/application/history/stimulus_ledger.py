"""Balanço de ESTÍMULOS × META — o que o atleta recebeu de cada família de
treino nas últimas semanas (limiar, VO2, longão, ritmo de prova, subida...),
como a intensidade REAL se distribuiu nas zonas de FC, e o que FALTA rumo ao
objetivo e à fase (semanas até a prova). É a base pro coach OFERECER o treino
certo ("faz 5 semanas sem limiar — rumo aos 10k, quinta é dia de 3x2km"), em
vez de escolher no escuro ou repetir o cardápio.

Puro/determinístico: planos das semanas (o que foi PRESCRITO) cruzados com as
corridas do arquivo (foi FEITO? — corrida no mesmo dia). Ver
[[project_cardapio_treinos]] e [[feedback_base_historico_sempre]]."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.clock import active_timezone, today_local
from app.domain.entities.activity import Activity
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan
from app.domain.value_objects.sports import is_run_sport

WINDOW_WEEKS = 8

# janela da distribuição de intensidade (dias) — recente o bastante pra valer
_ZONE_WINDOW_DAYS = 28

_MIN_DISTANCE_M = 1000

# famílias de estímulo, em ORDEM de classificação (o 1º que casar vence)
RACE = "prova"
TAPER = "ativação pré-prova"
RACE_PACE = "ritmo de prova / simulado"
HILLS = "subida / força"
FARTLEK = "fartlek"
THRESHOLD = "limiar"
VO2 = "VO2 / velocidade"
LONG = "longão"
PROGRESSION = "progressivo"
STRIDES = "acelerações / técnica"
STEADY = "rodagem moderada"
EASY = "rodagem leve / regenerativo"

_RULES: list[tuple[str, tuple[str, ...]]] = [
    (TAPER, ("pre-prova", "pre prova", "pos-prova", "pos prova", "ativacao",
             "soltura")),
    (RACE_PACE, ("simulado", "de prova", "pace alvo", "pace-alvo",
                 "ritmo alvo", "ritmo-alvo", "yasso", "michigan", "teste",
                 "contrarrelogio")),
    (RACE, ("prova",)),
    (HILLS, ("subida", "rampa", "morro", "hill", "kenyan", "descida",
             "ondulado", "trilha")),
    (FARTLEK, ("fartlek",)),
    (THRESHOLD, ("limiar", "threshold", "tempo run", "cruzeiro", "over-under",
                 "over under", "alternado", "cutdown", "surge", "ritmo forte")),
    (VO2, ("vo2", "velocidade", "piramide", "escada", "tiro", "sprint",
           "interval")),
    (LONG, ("longao", "longo", "long run")),
    (PROGRESSION, ("progress",)),
    (STRIDES, ("acelera", "stride", "educativ", "cadencia")),
    (STEADY, ("moderad", "steady")),
]

# o que a META pede (por distância) — as famílias-chave de cada prova
_NEEDS_BY_DISTANCE: list[tuple[float, tuple[str, ...]]] = [
    (5.0, (VO2, THRESHOLD, RACE_PACE, STRIDES)),
    (10.0, (THRESHOLD, VO2, LONG, RACE_PACE)),
    (21.1, (THRESHOLD, LONG, RACE_PACE, STEADY)),
    (99.0, (LONG, STEADY, THRESHOLD, RACE_PACE)),
]

# estímulos que ninguém deveria ficar semanas sem (economia/variação). SUBIDA
# não entra: fica fora do plano da semana, só no avulso quando o atleta pede
_GENERAL = (STRIDES, FARTLEK)

# famílias que contam como "qualidade" (não fica sem por muito tempo)
_QUALITY = {RACE_PACE, HILLS, FARTLEK, THRESHOLD, VO2, PROGRESSION}


@dataclass(slots=True)
class FamilyStat:

    family: str
    done: int
    missed: int
    last_done: date | None


@dataclass(slots=True)
class ZoneSplit:

    easy_pct: int      # Z1+Z2
    moderate_pct: int  # Z3 (zona cinzenta)
    hard_pct: int      # Z4+Z5
    runs: int


class StimulusLedger:

    @staticmethod
    def classify(workout_type: str) -> str:
        """Família de estímulo de um treino pelo nome (livre, da IA)."""

        norm = StimulusLedger._normalize(workout_type)

        # "longão progressivo/misto/com blocos" é longão (o volume manda)
        for family, cues in _RULES:

            if any(cue in norm for cue in cues):

                if family == PROGRESSION and ("longao" in norm or "longo" in norm):

                    return LONG

                return family

        return EASY

    @staticmethod
    def families(
        plans: list[TrainingPlan],
        activities: list[Activity],
        today: date,
        weeks: int = WINDOW_WEEKS,
    ) -> dict[str, FamilyStat]:
        """Por família: quantas sessões foram FEITAS, quantas furadas, e a
        última feita — na janela de `weeks` semanas até hoje."""

        from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher

        start = today - timedelta(weeks=weeks)

        runs = [
            a for a in activities
            if is_run_sport(a.sport) and (a.distance or 0) >= _MIN_DISTANCE_M
        ]

        # uma versão por semana (a mais recente gravada vence)
        by_week = {p.week_start: p for p in plans}

        stats: dict[str, FamilyStat] = {}

        for plan in by_week.values():

            # casamento do app inteiro (dia, depois distância, longão maior
            # conta) — casar só pelo dia contava furo de quem trocou o dia
            for session, act in WeeklyPlanMatcher.pairs(plan, runs):

                if getattr(session, "kind", "run") not in ("run", "walk", "run_walk"):

                    continue

                day = plan.session_date(session)

                if day < start or (day > today and act is None):

                    continue

                family = StimulusLedger.classify(session.workout_type)

                stat = stats.setdefault(family, FamilyStat(family, 0, 0, None))

                if act is not None:

                    stat.done += 1

                    done_day = StimulusLedger._local_day(act.start_date)

                    if stat.last_done is None or done_day > stat.last_done:

                        stat.last_done = done_day

                elif day < today:

                    stat.missed += 1

        return stats

    @staticmethod
    def zone_split(
        activities: list[Activity],
        today: date,
        max_hr: int | None = None,
        resting_hr: int | None = None,
    ) -> ZoneSplit | None:
        """Distribuição do TEMPO de corrida (últimos 28 dias) por faixa de
        esforço, pela FC média de cada corrida na reserva de FC DO atleta:
        leve < 70%, zona cinzenta 70-80%, forte >= 80%. Mesma régua pra todo
        o histórico — os minutos-por-zona gravados misturam réguas (fórmula de
        idade antes de 25/09, relógio depois) e distorciam a leitura. None sem
        FC máx/repouso (melhor calar que ler errado)."""

        if not max_hr or not resting_hr or max_hr <= resting_hr:

            return None

        reserve = max_hr - resting_hr

        easy_top = resting_hr + 0.70 * reserve

        hard_floor = resting_hr + 0.80 * reserve

        start = today - timedelta(days=_ZONE_WINDOW_DAYS)

        easy = moderate = hard = 0.0

        runs = 0

        for a in activities:

            hr = a.average_heartrate

            if not hr or not is_run_sport(a.sport) or not a.moving_time:

                continue

            if (a.distance or 0) < _MIN_DISTANCE_M:

                continue

            if StimulusLedger._local_day(a.start_date) < start:

                continue

            runs += 1

            minutes = a.moving_time / 60

            if hr < easy_top:

                easy += minutes

            elif hr < hard_floor:

                moderate += minutes

            else:

                hard += minutes

        total = easy + moderate + hard

        if not runs or total <= 0:

            return None

        return ZoneSplit(
            easy_pct=round(easy / total * 100),
            moderate_pct=round(moderate / total * 100),
            hard_pct=round(hard / total * 100),
            runs=runs,
        )

    @staticmethod
    def render(
        plans: list[TrainingPlan],
        activities: list[Activity],
        goal: TrainingGoal | None,
        today: date,
        max_hr: int | None = None,
        resting_hr: int | None = None,
    ) -> str:
        """Bloco pro coach: estímulos recebidos, intensidade real e LACUNAS
        rumo à meta/fase. Vazio sem plano nenhum na janela."""

        stats = StimulusLedger.families(plans, activities, today)

        if not stats:

            return ""

        lines = [
            f"BALANÇO DE ESTÍMULOS (últimas {WINDOW_WEEKS} semanas — feito/"
            "furado por família, cruzando plano × corrida real):"
        ]

        order = [f for f, _ in _RULES] + [EASY]

        for family in order:

            stat = stats.get(family)

            if stat is None or family in (TAPER,):

                continue

            last = (
                f", último há {StimulusLedger._ago(stat.last_done, today)}"
                if stat.last_done else ""
            )

            missed = f", furou {stat.missed}" if stat.missed else ""

            lines.append(f"- {family}: fez {stat.done}{missed}{last}")

        zones = StimulusLedger.zone_split(activities, today, max_hr, resting_hr)

        if zones:

            note = ""

            if zones.moderate_pct >= 30:

                note = (
                    " — MUITA zona cinzenta (cansa sem dar o estímulo nem do "
                    "leve nem do forte; leve mais leve, forte mais forte)"
                )

            elif zones.easy_pct < 65:

                note = " — pouco tempo leve pra absorver a carga"

            lines.append(
                f"- Intensidade real (FC média de cada corrida na reserva de "
                f"FC dele, {zones.runs} corridas em 4 sem): {zones.easy_pct}% "
                f"do tempo leve (<70%), {zones.moderate_pct}% zona cinzenta "
                f"(70-80%), {zones.hard_pct}% forte (>=80%){note}. É pela FC "
                "MÉDIA: tiro com pausa aparece mais leve do que foi."
            )

        gaps = StimulusLedger._gaps(stats, goal, today)

        if gaps:

            lines.append(gaps)

        lines.append(
            "USE ISTO PRA ESCOLHER E OFERECER o treino: priorize a lacuna mais "
            "relevante pra meta e pra fase, VARIE a forma dentro da família, e "
            "diga ao atleta POR QUE esse estímulo agora (a evolução × o "
            "objetivo). O corpo de hoje ainda manda na DOSE."
        )

        return "\n".join(lines)

    @staticmethod
    def for_profile(profile: str) -> str:
        """Render a partir do storage do atleta. Best-effort: falha vira ""."""

        try:

            from app.application.use_cases.build_training_goal import (
                BuildTrainingGoal,
            )
            from app.application.use_cases.load_runner_profile import (
                LoadRunnerProfile,
            )
            from app.infrastructure.persistence.activity_archive_repository import (
                ActivityArchiveRepository,
            )
            from app.infrastructure.persistence.weekly_plan_repository import (
                WeeklyPlanRepository,
            )

            repo = WeeklyPlanRepository()

            plans = list(repo.history(profile))

            current = repo.load(profile)

            if current is not None:

                plans.append(current)

            runner = LoadRunnerProfile.execute(profile)

            try:

                goal = BuildTrainingGoal.execute(runner)

            except Exception:

                goal = None

            activities = ActivityArchiveRepository().load_activities(profile)

            max_hr = resting_hr = None

            try:

                from app.application.history.hr_zone_resolver import (
                    HrZoneResolver,
                )

                zones = HrZoneResolver.for_profile(profile, runner, activities)

                # repouso REAL de hoje — o mesmo do teto aeróbico (o da
                # config do relógio envelhece)
                if zones is not None:

                    max_hr = zones.max_hr

                    resting_hr = (
                        HrZoneResolver.resting_now(profile) or zones.resting_hr
                    )

            except Exception as e:

                print(f"Zonas p/ balanço falharam p/ '{profile}': {e}")

            return StimulusLedger.render(
                plans, activities, goal, today_local(), max_hr, resting_hr,
            )

        except Exception as e:

            print(f"Balanço de estímulos falhou p/ '{profile}': {e}")

            return ""

    # ------------------------------------------------------------------

    @staticmethod
    def _gaps(
        stats: dict[str, FamilyStat],
        goal: TrainingGoal | None,
        today: date,
    ) -> str:
        """O que falta rumo à meta: famílias-chave da distância sem estímulo
        recente (4+ semanas), + a ênfase da FASE pelas semanas até a prova."""

        distance = goal.distance_km if goal and goal.distance_km else 10.0

        needs = next(n for limit, n in _NEEDS_BY_DISTANCE if distance <= limit)

        weeks_to_race = (
            (goal.race_date - today).days // 7
            if goal and goal.race_date and goal.race_date >= today else None
        )

        missing: list[str] = []

        # a mesma família pode estar nas duas listas (ex.: acelerações)
        for family in dict.fromkeys(needs + _GENERAL):

            stat = stats.get(family)

            last = stat.last_done if stat else None

            if last is None:

                missing.append(f"{family} (nenhum em {WINDOW_WEEKS} sem)")

            elif (today - last).days >= 28:

                missing.append(
                    f"{family} (último há {StimulusLedger._ago(last, today)})"
                )

        if weeks_to_race is None:

            phase = (
                "sem prova marcada: desenvolvimento geral — alterne limiar, "
                "VO2 e longão, com economia (acelerações)"
            )

        elif weeks_to_race > 12:

            phase = (
                f"prova em ~{weeks_to_race} sem (BASE): volume, longão, limiar; "
                "acelerações pra economia"
            )

        elif weeks_to_race > 4:

            phase = (
                f"prova em ~{weeks_to_race} sem (ESPECÍFICA): o ritmo de prova "
                "entra (blocos no pace-alvo), limiar/VO2 conforme a distância"
            )

        elif weeks_to_race > 1:

            phase = (
                f"prova em ~{weeks_to_race} sem (AFINAR): blocos no pace-alvo e "
                "UM simulado; volume começa a baixar"
            )

        else:

            phase = "semana da prova (POUPAR): só ativação curta no ritmo"

        # a PROVA que ancora (distância/data reais) — o goal.name é o objetivo
        # de fundo ("correr 21 km...") e confundia o rótulo com a prova de 15k
        if goal and goal.race_date:

            target = f" em {goal.target_time}" if goal.target_time else ""

            label = (
                f"prova de {distance:g} km{target} em "
                f"{goal.race_date:%d/%m/%Y}"
            )

        else:

            label = goal.name if goal and goal.name else f"{distance:g} km"

        text = f"Meta: {label} — fase: {phase}."

        if missing:

            text += " LACUNAS: " + "; ".join(missing) + "."

        return text

    @staticmethod
    def _ago(day: date, today: date) -> str:

        days = (today - day).days

        if days < 7:

            return f"{days} dia{'s' if days != 1 else ''}"

        weeks = days // 7

        return f"{weeks} sem"

    @staticmethod
    def _local_day(moment: datetime) -> date:

        if moment.tzinfo is None:

            return moment.date()

        return moment.astimezone(active_timezone()).date()

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = (text or "").lower()

        without = "".join(
            c for c in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(c) != "Mn"
        )

        return re.sub(r"\s+", " ", without)
