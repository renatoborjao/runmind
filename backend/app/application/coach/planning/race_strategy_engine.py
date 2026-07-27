"""Estratégia de prova: dado o objetivo (distância + tempo-alvo) e a forma
atual do atleta, monta o PLANO DE PACE da prova — pace-alvo, largada
controlada, negative split e abastecimento nas longas. Determinístico (a
matemática do pace é exata; nada de IA pra não arriscar número errado).

Serve on-demand ("como corro minha prova?") e alimenta os toques proativos
(semana da prova, véspera). Ver [[project_ideias_produto]]."""

from dataclasses import dataclass

from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_goal import TrainingGoal

# quanto abrir mais devagar / fechar mais forte que o pace médio (min/km).
# ~5 s/km pra cada lado: largada segura sem jogar tempo fora, final forte.
_SPLIT_OFFSET_MIN = 5 / 60

# a partir daqui a prova é longa o bastante pra abastecer (gel/carboidrato)
_FUELING_DISTANCE_KM = 15.0


@dataclass(slots=True)
class RacePacePlan:

    distance_km: float
    estimated: bool          # True = tempo veio da forma atual, não de um alvo
    total_minutes: float     # tempo-alvo (ou estimado) em minutos
    avg_pace_min: float      # pace médio (min/km)
    open_pace_min: float     # 1ª metade, controlado
    close_pace_min: float    # 2ª metade, mais forte
    halfway_minutes: float   # passagem na metade da distância


class RaceStrategyEngine:

    @staticmethod
    def build(
        runner_name: str,
        goal: TrainingGoal,
        metrics: RunnerMetrics | None = None,
    ) -> str | None:
        """Mensagem da estratégia, ou None se não dá pra montar (sem distância
        e sem tempo-alvo nem forma pra estimar)."""

        plan = RaceStrategyEngine.plan(goal, metrics)

        if plan is None:

            return None

        return RaceStrategyEngine._message(runner_name, goal, plan)

    @staticmethod
    def plan(
        goal: TrainingGoal,
        metrics: RunnerMetrics | None = None,
    ) -> RacePacePlan | None:

        distance = goal.distance_km or 0.0

        if distance <= 0:

            return None

        total_minutes = RaceStrategyEngine._target_minutes(goal, distance, metrics)

        if total_minutes is None:

            return None

        avg = total_minutes / distance

        open_pace = avg + _SPLIT_OFFSET_MIN
        close_pace = avg - _SPLIT_OFFSET_MIN

        # passagem na metade correndo a 1ª metade no pace controlado
        halfway = open_pace * (distance / 2)

        return RacePacePlan(
            distance_km=distance,
            estimated=goal.target_time is None,
            total_minutes=total_minutes,
            avg_pace_min=avg,
            open_pace_min=open_pace,
            close_pace_min=close_pace,
            halfway_minutes=halfway,
        )

    @staticmethod
    def _target_minutes(
        goal: TrainingGoal,
        distance: float,
        metrics: RunnerMetrics | None,
    ) -> float | None:
        """Minutos-alvo: do tempo declarado, senão estimado pela forma atual
        (pace de limiar ≈ ritmo de prova de ~10k). Sem nenhum dos dois, None."""

        parsed = RaceStrategyEngine._parse_time(goal.target_time)

        if parsed is not None:

            return parsed

        if metrics is not None and metrics.threshold_pace > 0:

            return metrics.threshold_pace * distance

        return None

    @staticmethod
    def _parse_time(target_time: str | None) -> float | None:
        """"00:50:00"/"50:00" -> minutos (float). Formato inválido -> None."""

        if not target_time:

            return None

        parts = target_time.split(":")

        try:

            nums = [int(p) for p in parts]

        except ValueError:

            return None

        if len(nums) == 3:

            h, m, s = nums

        elif len(nums) == 2:

            h, m, s = 0, nums[0], nums[1]

        else:

            return None

        total = h * 60 + m + s / 60

        return total if total > 0 else None

    @staticmethod
    def _message(
        runner_name: str,
        goal: TrainingGoal,
        plan: RacePacePlan,
    ) -> str:

        distance = RaceStrategyEngine._fmt_distance(plan.distance_km)
        avg = PaceFormatter.format(plan.avg_pace_min)
        open_pace = PaceFormatter.format(plan.open_pace_min)
        close_pace = PaceFormatter.format(plan.close_pace_min)
        half_km = RaceStrategyEngine._fmt_distance(plan.distance_km / 2)
        halfway = RaceStrategyEngine._fmt_duration(plan.halfway_minutes)

        if plan.estimated:

            abertura = (
                f"Pelo seu ritmo atual, {runner_name}, algo perto de "
                f"*{RaceStrategyEngine._fmt_duration(plan.total_minutes)}* nos "
                f"{distance} km é realista. Se tiver um tempo-alvo, me fala que "
                "eu recalibro. Mas já vai a estratégia:"
            )

        else:

            abertura = (
                f"🏁 Estratégia pra sua prova, {runner_name} "
                f"({distance} km em "
                f"{RaceStrategyEngine._fmt_duration(plan.total_minutes)}):"
            )

        linhas = [
            abertura,
            "",
            f"🎯 Pace-alvo médio: *{avg}/km*",
            "",
            "Como correr:",
            f"• Largada CONTROLADA — primeira metade em ~{open_pace}/km. "
            "Todo mundo sai rápido demais; segurar aqui é o que salva o final.",
            f"• Segunda metade em ~{close_pace}/km — é onde você passa os "
            "outros em vez de ser passado.",
            f"• Passagem nos {half_km} km: ~{halfway} (se chegar muito antes "
            "disso, segura; muito depois, é hora de acelerar).",
        ]

        if plan.distance_km >= _FUELING_DISTANCE_KM:

            linhas += [
                "",
                "⚡ Como é longa: leve carboidrato (gel/isotônico) a cada "
                "~40-45 min e hidrate desde cedo, antes de sentir sede.",
            ]

        linhas += [
            "",
            "O ritmo está dentro do que você treinou — confia no plano. 🚀",
        ]

        return "\n".join(linhas)

    @staticmethod
    def _fmt_distance(km: float) -> str:

        return f"{km:.0f}" if abs(km - round(km)) < 0.05 else f"{km:.1f}"

    @staticmethod
    def _fmt_duration(minutes: float) -> str:
        """Minutos (float) -> 'H:MM:SS' (>=1h) ou 'MM:SS'."""

        total_sec = round(minutes * 60)
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)

        if h > 0:

            return f"{h}:{m:02d}:{s:02d}"

        return f"{m}:{s:02d}"
