"""Debrief pós-prova: quando o atleta CORRE a prova-alvo, o coach não manda o
feedback de treino comum — manda uma análise especial do DIA: resultado vs
meta, comemora ou consola com honestidade, e aponta o próximo passo. Depois,
apaga a data da prova (ela foi cumprida) pra não reaparecer.

Determinístico (tempo e pace são exatos). Puro reconhecimento — não mexe em
plano. Ver [[project_ideias_produto]]."""

from app.application.coach.planning.race_strategy_engine import (
    RaceStrategyEngine,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# tolerância de distância pra casar a atividade com a prova (±15%): uma prova
# de 10 km raramente marca exatos 10.000 m no relógio
_DISTANCE_TOLERANCE = 0.15

# margem de dias em torno da data cadastrada (fuso/adiamento de 1 dia)
_DATE_TOLERANCE_DAYS = 1

# quão perto da meta ainda conta como "quase lá" (2% do tempo)
_NEAR_MISS_RATIO = 1.02


class RaceDebrief:

    @staticmethod
    def is_target_race(runner: RunnerProfile, enriched_activity) -> bool:
        """ESTA atividade é a prova-alvo? (só leitura — NÃO consome a data).
        O TrainingCompletedEvent usa isso pra saber que o dia é da PROVA e
        calar o feedback de treino comum."""

        goal = BuildTrainingGoal.execute(runner)

        if goal.race_date is None or enriched_activity is None:

            return False

        activity = getattr(enriched_activity, "activity", None)

        if activity is None or not activity.moving_time or not activity.distance:

            return False

        return RaceDebrief._is_the_race(activity, goal)

    @staticmethod
    async def after_feedback(
        profile: str,
        runner: RunnerProfile,
        enriched_activity,
    ) -> str | None:
        """Devolve o debrief se ESTA atividade é a prova-alvo; senão None.
        Consome a prova (apaga a data) quando reconhece."""

        if not RaceDebrief.is_target_race(runner, enriched_activity):

            return None

        goal = BuildTrainingGoal.execute(runner)

        # a prova foi cumprida: apaga a data pra não redisparar nem confundir
        # o planejamento seguinte (o objetivo/goal continua pra a próxima)
        RunnerProfileRepository().update_fields(profile, {"race_date": None})

        return RaceDebrief._message(runner, enriched_activity, goal)

    @staticmethod
    def _is_the_race(activity, goal) -> bool:

        distance_km = activity.distance / 1000

        near_distance = abs(distance_km - goal.distance_km) <= (
            goal.distance_km * _DISTANCE_TOLERANCE
        )

        days_off = abs((activity.start_date.date() - goal.race_date).days)

        return near_distance and days_off <= _DATE_TOLERANCE_DAYS

    @staticmethod
    def _message(runner, enriched, goal) -> str:
        """O RELATÓRIO da prova: veredito (vs meta) + números do dia + parciais
        km a km. É o que o atleta vê no lugar do feedback de treino comum — a
        prova não é 'mais um treino'."""

        activity = enriched.activity

        distance_km = activity.distance / 1000
        actual_min = activity.moving_time / 60
        actual = RaceDebrief._fmt_duration(actual_min)
        pace = PaceFormatter.format(actual_min / distance_km)

        header = RaceDebrief._verdict(runner.name, actual_min, actual, goal)

        parts = [header, RaceDebrief._stats_line(enriched, distance_km, actual, pace)]

        splits = RaceDebrief._splits_block(enriched)

        if splits:

            parts.append(splits)

        parts.append(
            "Agora é RECUPERAR: uns dias leves ou de folga, sem culpa — o corpo "
            "pede pra assimilar o esforço. Quando bater a vontade da próxima "
            "meta, me fala que a gente traça o caminho. 👊"
        )

        return "\n\n".join(parts)

    @staticmethod
    def _stats_line(enriched, distance_km, actual, pace) -> str:
        """Uma linha compacta com os números do dia (distância/tempo/pace + FC +
        cadência quando o relógio deu)."""

        activity = enriched.activity

        line = f"📊 {distance_km:.1f} km em *{actual}* — pace médio {pace}/km"

        avg_hr = getattr(activity, "average_heartrate", None)

        if avg_hr:

            line += f" · FC {int(avg_hr)}"

            max_hr = getattr(activity, "max_heartrate", None)

            if max_hr:

                line += f"/{int(max_hr)}"

            line += " bpm"

        structure = getattr(enriched, "structure", None)

        if structure is not None and getattr(structure, "cadence_spm", None):

            line += f" · cadência {structure.cadence_spm} ppm"

        return f"{line}."

    @staticmethod
    def _splits_block(enriched) -> str | None:
        """Parciais km a km (pace + FC), como no relatório de treino — a prova
        merece os splits também."""

        structure = getattr(enriched, "structure", None)

        if structure is None or not getattr(structure, "km_splits", None):

            return None

        km_hr = getattr(structure, "km_hr", []) or []

        lines = ["⏱️ Parciais por km"]

        for index, split_pace in enumerate(structure.km_splits):

            line = f"km {index + 1}: {PaceFormatter.format(split_pace)} min/km"

            if index < len(km_hr) and km_hr[index]:

                line += f" · {km_hr[index]} bpm"

            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def _verdict(name, actual_min, actual, goal) -> str:
        """Comemora/consola conforme o resultado vs a meta — honesto sempre."""

        target_min = RaceStrategyEngine._parse_time(goal.target_time)

        if target_min is None:

            return (
                f"Você CRUZOU A LINHA, {name}! 🏁🎉 Prova concluída — isso por "
                "si só já é uma baita conquista. Orgulho de ter treinado contigo."
            )

        target = RaceDebrief._fmt_duration(target_min)

        if actual_min <= target_min:

            return (
                f"VOCÊ CONSEGUIU, {name}!! 🏆🎉 Cruzou em {actual} — a meta era "
                f"{target} e você BATEU. Todo aquele trabalho virou resultado. "
                "Que dia!"
            )

        if actual_min <= target_min * _NEAR_MISS_RATIO:

            return (
                f"Que prova, {name}! 🔥 {actual} — a meta era {target}, você "
                "chegou pertíssimo. De tirar o chapéu; o próximo degrau tá logo "
                "ali."
            )

        return (
            f"Prova concluída, {name}! 🏁 Foi {actual} (a meta era {target}). "
            "Hoje não saiu o tempo, e tudo bem — prova é dia, e cada uma ensina. "
            "Você foi lá e encarou, isso é o que constrói o próximo PR."
        )

    @staticmethod
    def _fmt_duration(minutes: float) -> str:

        total_sec = round(minutes * 60)
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)

        if h > 0:

            return f"{h}:{m:02d}:{s:02d}"

        return f"{m}:{s:02d}"
