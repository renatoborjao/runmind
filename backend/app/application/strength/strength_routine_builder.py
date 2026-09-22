"""O coach MONTA a rotina de fortalecimento do atleta a partir da biblioteca
([[project_fortalecimento]]). Determinístico e ciente do plano — não decide no
vácuo ([[feedback_base_historico_sempre]]):

- DIAS: 2x/semana, encaixados pra NÃO atrapalhar a corrida. Regra de treinador:
  força no MESMO dia do treino forte (dia duro continua duro) ou em dia leve;
  NUNCA na véspera de longão/qualidade (perna tem que chegar descansada).
- CONTEÚDO: conjunto equilibrado pra corredor (glúteo/quadril + core + perna +
  panturrilha), dose pelo nível (iniciante faz menos série).
- VARIEDADE: alterna as variações semana a semana (não engessa — [[feedback_tudo_dinamico]]).

Começa determinístico; a IA do plano emitir isso é evolução futura."""

from app.application.home.home_summary_builder import _kind
from app.application.strength.strength_library import EXERCISES
from app.core.clock import today_local, use_athlete_timezone
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

_WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]
_DAY_PT = {
    "Monday": "Segunda", "Tuesday": "Terça", "Wednesday": "Quarta",
    "Thursday": "Quinta", "Friday": "Sexta", "Saturday": "Sábado",
    "Sunday": "Domingo",
}

# biblioteca indexada por id, pra montar os blocos com nome/alvo/imagens/dicas
_BY_ID = {e["id"]: e for e in EXERCISES}

# esqueleto do treino do corredor: um de cada eixo, com 2 variações que a gente
# alterna por semana (variedade sem perder o foco). (id, reps).
_SLOTS = [
    # glúteo/quadril
    [("single_leg_glute_bridge", "10 cada perna"), ("hip_abduction_band", "12 cada lado")],
    # core
    [("plank", "30–45 s"), ("superman", "12")],
    # core lateral / estabilidade de quadril
    [("side_plank", "25–35 s cada lado"), ("glute_bridge", "15")],
    # perna (unilateral)
    [("walking_lunge", "10 cada perna"), ("split_squat", "10 cada perna")],
    # panturrilha
    [("calf_raise", "15"), ("step_up", "10 cada perna")],
]


class StrengthRoutineBuilder:

    @staticmethod
    def build(profile: str) -> dict:

        runner = RunnerProfileRepository().load(profile)

        use_athlete_timezone(getattr(runner, "timezone", None))

        plan = WeeklyPlanRepository().load(profile)

        sessions = {s.day: s for s in plan.sessions} if plan else {}

        days = StrengthRoutineBuilder._pick_days(sessions, runner)

        week = today_local().isocalendar()[1]

        sets = 2 if (getattr(runner, "weekly_training_days", 3) or 3) <= 2 else 3

        exercises = StrengthRoutineBuilder._routine(week, sets)

        return {
            "days": days,
            "days_pt": [_DAY_PT[d] for d in days],
            "frequency": len(days),
            "sets": sets,
            "note": StrengthRoutineBuilder._note(days, sessions),
            "exercises": exercises,
        }

    # ------------------------------------------------------------------

    @staticmethod
    def _pick_days(sessions: dict, runner) -> list[str]:
        """2 dias/semana pra força, sem atrapalhar a corrida. Prefere colar no
        dia forte (duro+duro) ou dia leve; foge da VÉSPERA de longão/qualidade e
        do próprio dia de longão. Espaça os dois. Fallback sem plano: dias de
        corrida preferidos, ou ter/sex."""

        kinds = {d: _kind(s.workout_type) for d, s in sessions.items()}

        scored: list[tuple[int, str]] = []

        for i, day in enumerate(_WEEKDAYS):

            nxt = _WEEKDAYS[(i + 1) % 7]

            # véspera de treino forte: perna tem que chegar fresca → fora
            if kinds.get(nxt) in ("tiro", "long"):

                continue

            k = kinds.get(day)

            if k == "tiro":

                score = 4          # dia forte: empilha (mantém o duro duro)

            elif k == "rod":

                score = 3          # dia leve de corrida: ótimo

            elif k is None:

                score = 2          # descanso: ok

            else:  # long

                score = 1          # dia do longão já é bastante

            scored.append((score, day))

        if len(scored) < 2:

            return StrengthRoutineBuilder._fallback_days(runner)

        scored.sort(key=lambda x: (-x[0], _WEEKDAYS.index(x[1])))

        # pega o melhor e, pro 2º, o melhor que esteja espaçado (≥2 dias)
        first = scored[0][1]

        rest = [d for _, d in scored[1:]]

        second = next(
            (d for d in rest if StrengthRoutineBuilder._gap(first, d) >= 2),
            rest[0] if rest else first,
        )

        return sorted({first, second}, key=_WEEKDAYS.index)

    @staticmethod
    def _gap(a: str, b: str) -> int:
        """Menor distância (em dias) entre dois dias da semana, circular."""

        d = abs(_WEEKDAYS.index(a) - _WEEKDAYS.index(b))

        return min(d, 7 - d)

    @staticmethod
    def _fallback_days(runner) -> list[str]:

        pref = [d for d in getattr(runner, "preferred_running_days", []) if d in _WEEKDAYS]

        if len(pref) >= 2:

            pref.sort(key=_WEEKDAYS.index)

            return [pref[0], pref[len(pref) // 2 if len(pref) > 2 else 1]]

        return ["Tuesday", "Friday"]

    @staticmethod
    def _routine(week: int, sets: int) -> list[dict]:
        """Um exercício por eixo; alterna a variação pela paridade da semana."""

        out: list[dict] = []

        for variants in _SLOTS:

            ex_id, reps = variants[week % len(variants)]

            base = _BY_ID.get(ex_id)

            if not base:

                continue

            out.append(
                {
                    "id": base["id"],
                    "name": base["name"],
                    "category": base["category"],
                    "target": base["target"],
                    "equipment": base["equipment"],
                    "images": base["images"],
                    "cues": base["cues"],
                    "why": base["why"],
                    # enriquecimento (erro comum/onde sentir/níveis/respiração)
                    # também na carta da rotina — mesmo card do app
                    "common_mistake": base.get("common_mistake"),
                    "feel_where": base.get("feel_where"),
                    "regression": base.get("regression"),
                    "progression": base.get("progression"),
                    "breathing": base.get("breathing"),
                    "execution": base.get("execution"),
                    "sets": sets,
                    "reps": reps,
                    "prescription": f"{sets} x {reps}",
                }
            )

        return out

    @staticmethod
    def _note(days: list[str], sessions: dict) -> str:

        dias = " e ".join(_DAY_PT[d] for d in days)

        return (
            f"O coach montou sua força pra {dias} — encaixada pra não pesar nos "
            f"seus treinos fortes. Faça na ordem, descansando ~1 min entre as "
            f"séries. Some ao fim de um treino leve ou num dia de descanso."
        )
