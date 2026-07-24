from datetime import datetime, timedelta
from uuid import uuid4

from app.core.clock import now_local
from app.domain.entities.coach_learning import CoachLearning
from app.infrastructure.persistence.coach_learning_repository import (
    CoachLearningRepository,
)

# quantas semanas um aprendizado vale sem nova evidência. 8 semanas: longo o
# bastante pra sobreviver a um bloco de treino, curto o bastante pra uma
# verdade velha ("não corre 5 km") não virar âncora quando o atleta evolui.
LEARNING_TTL_WEEKS = 8

# no máximo isso no contexto do plano (evita inflar o prompt); os mais
# recentes primeiro
MAX_LEARNINGS_IN_CONTEXT = 12


class CoachLearningService:
    """Aplica as operações destiladas ao fim da semana e renderiza os
    aprendizados vivos para o contexto do plano. Espelha o
    RunnerMemoryService, mas com validade (TTL) e reconfirmação."""

    @staticmethod
    def process(
        profile: str,
        ops: dict,
        level: str | None = None,
        goal_kind: str | None = None,
    ) -> None:
        """add/archive/reconfirm no repositório. Novos aprendizados nascem
        com validade de LEARNING_TTL_WEEKS; reconfirmados têm a validade
        empurrada adiante."""

        repo = CoachLearningRepository()

        now = now_local()

        expires_at = CoachLearningService._expiry(now)

        for item in ops.get("add", []):

            repo.add(
                profile,
                CoachLearning(
                    id=f"cl-{uuid4().hex[:8]}",
                    category=item["category"],
                    content=item["content"],
                    source="weekly_distillation",
                    created_at=now.isoformat(),
                    expires_at=expires_at,
                    level=level,
                    goal_kind=goal_kind,
                ),
            )

        repo.reconfirm(
            profile,
            ops.get("reconfirm", []),
            expires_at,
        )

        repo.archive(
            profile,
            ops.get("archive", []),
        )

    @staticmethod
    def render(
        profile: str,
    ) -> str:
        """Aprendizados vivos formatados pro contexto do plano — seção
        DISTINTA da memória evolutiva (aquela é o que ele DIZ; esta é o que
        ele FAZ). String vazia quando não há nada."""

        learnings = CoachLearningRepository().active(profile)

        if not learnings:

            return ""

        recent = learnings[-MAX_LEARNINGS_IN_CONTEXT:]

        lines = [
            "O que o coach aprendeu observando ELE (comportamento e "
            "resultado, não o que ele fala):"
        ]

        for entry in recent:

            registered = datetime.fromisoformat(
                entry.created_at
            ).strftime("%d/%m")

            lines.append(
                f"- [{entry.category}] {entry.content} ({registered})"
            )

        return "\n".join(lines)

    @staticmethod
    def _expiry(now: datetime) -> str:

        return (now + timedelta(weeks=LEARNING_TTL_WEEKS)).isoformat()
