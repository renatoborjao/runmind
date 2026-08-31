"""A META do atleta é ACIONÁVEL (dá pra periodizar) ou está VAGA? Sem uma prova/
distância com prazo, o coach não tem como estruturar de verdade — fica em base
genérica. O Hélio é o caso: perfil diz "saúde", a memória diz "prova de 10 km",
e não há distância/data cravada. Aqui a gente DETECTA a lacuna; quem pergunta é
o coach (uma vez, governado). Puro/determinístico.

Ver [[project_reconciliacao_coach]], [[project_multiplos_objetivos]] e
[[feedback_orientar_nao_mandar]]."""

from dataclasses import dataclass
from datetime import date

from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_goal import TrainingGoal

ACTIONABLE, OPEN, STALE, VAGUE = "actionable", "open", "stale", "vague"


@dataclass(slots=True)
class GoalClarity:

    verdict: str                       # actionable | open | stale | vague
    has_explicit_distance: bool
    has_future_date: bool
    has_time: bool
    latent_distance_hint: str | None   # prova mencionada na memória, sem estrutura
    passed_race_label: str | None = None   # a prova que JÁ passou (verdict stale)


class GoalClarityChecker:

    @staticmethod
    def assess(
        runner: RunnerProfile,
        goal: TrainingGoal,
        memory_objectives: list[str] | None = None,
        today: date | None = None,
    ) -> GoalClarity:
        """- actionable: distância concreta + data FUTURA (dá pra periodizar);
        - stale: tinha uma prova, mas a DATA já PASSOU — o alvo expirou, hora
          de perguntar o próximo;
        - open: distância-alvo sem data (nunca teve) — progressão contínua, NÃO
          cutuca;
        - vague: sem alvo concreto (saúde/genérico) — vale perguntar 1x."""

        today = today or today_local()

        explicit = (
            BuildTrainingGoal._parse_distance(runner.target_race) is not None
            or BuildTrainingGoal._parse_distance(runner.goal) is not None
        )

        future_date = goal.race_date is not None and goal.race_date > today

        past_date = goal.race_date is not None and goal.race_date <= today

        has_time = bool(goal.target_time)

        hint = None

        for text in memory_objectives or []:

            km = BuildTrainingGoal._parse_distance(text)

            if km is not None:

                hint = GoalClarityChecker._km_label(km)

                break

        passed_label = None

        if explicit and future_date:

            verdict = ACTIONABLE

        elif past_date:

            verdict = STALE

            passed_label = GoalClarityChecker._km_label(goal.distance_km)

        elif explicit:

            verdict = OPEN

        else:

            verdict = VAGUE

        return GoalClarity(
            verdict, explicit, future_date, has_time, hint, passed_label
        )

    @staticmethod
    def _km_label(km: float) -> str:

        if abs(km - 21.0975) < 0.6:

            return "meia maratona"

        if abs(km - 42.195) < 0.5:

            return "maratona"

        return f"{km:.0f} km" if abs(km - round(km)) < 0.05 else f"{km:.1f} km"


def goal_clarity_message(runner_name: str, clarity: GoalClarity) -> str:
    """A pergunta do coach pra cravar a meta. Vazia quando não é o caso ('vague'
    e 'stale' perguntam; 'actionable'/'open' não). Orientar, não mandar."""

    if clarity.verdict == STALE:

        prova = clarity.passed_race_label or "tua última prova"

        return (
            f"{runner_name}, teu foco era {prova} e essa data já passou 🏁 Bora "
            "mirar o próximo? Me diz se quer outra prova (distância + quando) — "
            "que eu periodizo — ou se prefere seguir num ciclo de base/saúde por "
            "enquanto. Só pra eu montar teu plano com um norte."
        )

    if clarity.verdict != VAGUE:

        return ""

    if clarity.latent_distance_hint:

        return (
            f"{runner_name}, uma dúvida pra eu te montar o melhor plano 🎯 Teu "
            "foco agora é saúde/condicionamento, ou você quer mirar um "
            f"{clarity.latent_distance_hint} de verdade? Se for prova, me diz a "
            "distância e até quando (e um tempo-alvo, se tiver) que eu periodizo "
            "certinho. Se for saúde mesmo, também é ótimo — só me confirma."
        )

    return (
        f"{runner_name}, pra eu calibrar teu treino do jeito certo 🎯 você quer "
        "trabalhar rumo a uma meta específica (uma prova/distância com prazo), "
        "ou seguimos com foco em saúde e evolução contínua? Qualquer um serve — "
        "só muda como eu monto o teu plano."
    )
