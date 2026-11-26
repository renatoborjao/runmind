"""PAUSA pedida pelo atleta ("vamos dar uma pausa nos treinos"). Diferente de pular
um treino ou a semana: aqui o coach não monta nem envia plano nenhum até o PRÓPRIO
atleta pedir pra voltar — sem data que a encerre sozinha, mesmo que ele cite uma
("até ano que vem"). Quem liga e desliga é a decisão do cérebro (ações pause/resume);
os geradores e os proativos de plano só consultam `runner.paused_since`.

Bug de origem (Mauricio, 25/11): a pausa virou um "pular a semana" mais uma nota de
memória, e o domingo geraria um plano novo do mesmo jeito."""

from datetime import date

from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.domain.memory_lifecycle import MemoryLifecycle
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# `source` do plano vazio devolvido a quem pede o plano durante a pausa
PAUSED_SOURCE = "pausa"


class TrainingPause:

    @staticmethod
    def start(profile: str, runner: RunnerProfile, today: date) -> None:
        """Liga a pausa. Já pausado: mantém a data do primeiro pedido."""

        since = runner.paused_since or today.isoformat()

        RunnerProfileRepository().update_fields(profile, {"paused_since": since})

        runner.paused_since = since

    @staticmethod
    def end(profile: str, runner: RunnerProfile) -> bool:
        """Encerra a pausa (o atleta pediu pra voltar) e arquiva as notas de memória
        que falavam dela — senão o plano novo leria "pausa até 31/12". Devolve False
        se não havia pausa."""

        since = runner.paused_since

        if not since:

            return False

        RunnerProfileRepository().update_fields(profile, {"paused_since": None})

        runner.paused_since = None

        try:

            repository = RunnerMemoryRepository()

            repository.archive(profile, [
                entry.id for entry in repository.active(profile)
                if entry.created_at[:10] >= since
                and MemoryLifecycle.is_absence(entry.category, entry.content)
            ])

        except Exception as e:  # noqa: BLE001 — a memória não segura a volta

            print(f"Memória da pausa não arquivada p/ '{profile}': {e}")

        return True

    @staticmethod
    def coach_line(runner: RunnerProfile) -> str:
        """O fato pro coach (dossiê). Vazio sem pausa."""

        if not getattr(runner, "paused_since", None):

            return ""

        since = date.fromisoformat(runner.paused_since)

        return (
            f"TREINOS EM PAUSA desde {since:%d/%m} a pedido dele: o sistema NÃO monta "
            "nem envia plano (nem no domingo) até ELE pedir pra voltar, mesmo que tenha "
            "citado uma data. Não cobre treino, não ofereça plano nem dia extra e não "
            "prometa plano. O que ele correr é treino livre."
        )

    @staticmethod
    def athlete_message(runner_name: str) -> str:
        """A resposta a quem pergunta pelo plano durante a pausa."""

        return (
            f"⏸️ {runner_name}, teus treinos estão em pausa a teu pedido, então não tem "
            "plano montado. Quando quiser voltar, é só me chamar aqui. 💪"
        )

    @staticmethod
    def empty_plan(runner: RunnerProfile, objective: str, week_start: date) -> TrainingPlan:
        """A semana de quem está em pausa: sem treinos e sem nada gravado."""

        return TrainingPlan(
            athlete_name=runner.name,
            objective=objective,
            phase="PAUSA",
            weekly_volume=0.0,
            running_days=[],
            week_start=week_start,
            sessions=[],
            source=PAUSED_SOURCE,
        )
