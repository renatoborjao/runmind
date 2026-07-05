import json

from google.genai import types

from app.core.config import get_settings
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini.client import generate_text
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

MAX_OUTPUT_TOKENS = 400

# alerta longo demais polui a mensagem do treino; corta com folga
MAX_NOTE_CHARS = 140

# A IA só REDUZ carga (nunca aumenta) e não abaixo destes limites — o motor
# determinístico segue sendo o teto; a IA apara o excesso pra este atleta.
MIN_KEEP_FRACTION = 0.4   # nunca corta pra menos de 40% do planejado
MIN_DISTANCE_KM = 1.0

PROMPT_TEMPLATE = """Você é um treinador de corrida experiente revisando um \
plano gerado automaticamente, para garantir que ele é REALISTA e SEGURO para
este atleta específico.

ATLETA:
{athlete}

PLANO DA SEMANA (uma sessão por linha):
{sessions}

Para CADA sessão que for claramente irreal ou insegura para este atleta
(ex.: correr contínuo além do que ele aguenta, volume/intensidade alta demais
para iniciante de alto peso, ritmo incompatível com a capacidade):
- retorne um alerta CURTO e prático em "note" (o que fazer no lugar);
- se der pra tornar a sessão viável só REDUZINDO a distância, informe um teto
  seguro em km em "suggested_max_km" (sempre MENOR que o planejado, nunca
  maior; omita se não fizer sentido reduzir).

Se o plano estiver adequado, retorne lista vazia.

Responda APENAS com JSON:
{{"concerns": [{{"day": "Monday", "note": "...", "suggested_max_km": 5.0}}]}}
"""


class PlanRealismReviewer:
    """IA revisora: por cima do plano determinístico, marca as sessões
    irreais para o atleta com um alerta e pode APARAR a distância (só pra
    menos, com piso). O determinístico segue sendo o teto; se a IA falhar,
    o plano segue intacto."""

    @staticmethod
    async def ensure_reviewed(
        profile: str,
        runner: RunnerProfile,
        plan: TrainingPlan,
    ) -> TrainingPlan:
        """Revisa o plano uma única vez por semana (idempotente) e
        persiste os alertas. Falha da IA nunca quebra a entrega."""

        if (
            plan.source != "runmind"
            or not plan.sessions
            or plan.reviewed
        ):

            return plan

        try:

            concerns = await PlanRealismReviewer._ask(runner, plan)

        except Exception as e:

            # indisponibilidade da IA não pode travar a entrega do plano;
            # deixa reviewed=False pra tentar de novo na próxima entrega
            print(f"Falha na revisão do plano de '{profile}': {e}")

            return plan

        PlanRealismReviewer._apply(plan, concerns)

        plan.reviewed = True

        WeeklyPlanRepository().save(profile, plan)

        return plan

    # ==========================================================

    @staticmethod
    async def _ask(
        runner: RunnerProfile,
        plan: TrainingPlan,
    ) -> list[dict]:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            athlete=PlanRealismReviewer._describe_athlete(runner),
            sessions=PlanRealismReviewer._describe_sessions(plan),
        )

        raw = await generate_text(
            model=settings.gemini_extract_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
        )

        return PlanRealismReviewer._parse(raw)

    @staticmethod
    def _describe_athlete(runner: RunnerProfile) -> str:

        lines = [
            f"- Nome: {runner.name}",
            f"- Idade: {runner.age} anos",
        ]

        bmi = PlanRealismReviewer._bmi(runner)

        if bmi:

            lines.append(
                f"- Peso/altura: {runner.weight:.0f} kg, "
                f"{runner.height:.2f} m (IMC {bmi:.0f})"
            )

        if runner.mobility:

            mobility_pt = {
                "walker": "só caminha hoje",
                "run_walker": "hoje faz trote e caminhada",
                "runner": "já corre contínuo (pouco)",
            }.get(runner.mobility, runner.mobility)

            lines.append(f"- Como se move: {mobility_pt}")

        if runner.continuous_run_minutes:

            lines.append(
                "- Corre sem parar por cerca de "
                f"{runner.continuous_run_minutes:.0f} min"
            )

        lines.append(f"- Objetivo: {runner.goal}")

        return "\n".join(lines)

    @staticmethod
    def _describe_sessions(plan: TrainingPlan) -> str:

        lines = []

        for session in plan.sessions:

            if session.planned_distance_km:

                size = f"{session.planned_distance_km:.1f} km"

            elif session.planned_duration_minutes:

                size = f"{session.planned_duration_minutes} min"

            else:

                size = "—"

            pace = ""

            if session.target_pace_min and session.target_pace_max:

                pace = (
                    f", ritmo {session.target_pace_min}"
                    f"–{session.target_pace_max}/km"
                )

            intervals = ""

            if session.intervals:

                iv = session.intervals

                intervals = (
                    f", intervalos {iv.get('reps')}x "
                    f"(trote {iv.get('trot_sec')}s + "
                    f"caminhada {iv.get('walk_sec')}s)"
                )

            lines.append(
                f"{session.day}: {session.workout_type} · {size}"
                f"{pace}{intervals}"
            )

        return "\n".join(lines)

    @staticmethod
    def _apply(
        plan: TrainingPlan,
        concerns: list[dict],
    ) -> None:

        by_day = {
            session.day.lower(): session
            for session in plan.sessions
        }

        for concern in concerns:

            day = str(concern.get("day", "")).lower()

            note = str(concern.get("note", "")).strip()

            session = by_day.get(day)

            if session is None or not note:

                continue

            session.adjusted = True

            session.adjustment_reason = note[:MAX_NOTE_CHARS]

            PlanRealismReviewer._cap_distance(
                session,
                concern.get("suggested_max_km"),
            )

    @staticmethod
    def _cap_distance(session, suggested) -> None:
        """Reduz a distância planejada para o teto sugerido pela IA — só
        pra menos e nunca abaixo do piso (40% do planejado ou 1 km). Sessão
        sem distância (run/walk, medida em tempo) não é mexida aqui."""

        if not isinstance(suggested, (int, float)):

            return

        planned = session.planned_distance_km

        if not planned:

            return

        floor = max(MIN_DISTANCE_KM, round(planned * MIN_KEEP_FRACTION, 1))

        capped = round(min(max(suggested, floor), planned), 1)

        if capped < planned:

            session.planned_distance_km = capped

    @staticmethod
    def _parse(raw: str) -> list[dict]:

        try:

            data = json.loads(raw)

        except (json.JSONDecodeError, TypeError):

            return []

        if not isinstance(data, dict):

            return []

        concerns = data.get("concerns", [])

        if not isinstance(concerns, list):

            return []

        return [item for item in concerns if isinstance(item, dict)]

    @staticmethod
    def _bmi(runner: RunnerProfile) -> float:

        if not runner.height:

            return 0.0

        return runner.weight / (runner.height ** 2)
