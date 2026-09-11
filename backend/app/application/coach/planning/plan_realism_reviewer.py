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
plano gerado automaticamente. Sua função é uma REDE DE SEGURANÇA: só intervém no
que for CLARAMENTE irreal ou inseguro para este atleta. Na dúvida, NÃO sinalize —
um plano de qualidade bem dosado deve passar limpo.

ATLETA:
{athlete}
{capacity_section}
PLANO DA SEMANA (uma sessão por linha):
{sessions}

A CAPACIDADE PROJETADA (quando informada acima) É A REFERÊNCIA DE REALISMO E
MANDA sobre peso/idade: ela reflete o que o atleta REALMENTE sustenta hoje. Um
atleta mais pesado que a projeção mostra correndo 10K a 5:10/km SUSTENTA esse
ritmo — NÃO é "agressivo demais pelo peso". Só o que a projeção NÃO sustenta é
que é irreal.

Sinalize APENAS nestes casos, com um "note" CURTO e prático (o que fazer no
lugar), ajuste sempre GRADUAL, nunca reescrevendo o ritmo como ordem:
1. VOLUME/CONTÍNUO inseguro pra este atleta (ex.: iniciante de alto peso ou
   run/walk correndo contínuo muito além do que aguenta) — aí, e SÓ aí, se der
   pra viabilizar reduzindo a distância, informe "suggested_max_km" (sempre
   MENOR que o planejado; NUNCA em sessão medida por tempo/minutos).
2. RITMO DE PROVA / contínuo no ritmo-alvo da meta prescrito MAIS RÁPIDO do que a
   projeção sustenta hoje (ex.: prescrever ritmo de meia bem abaixo do que o
   relógio projeta pra meia).

NUNCA sinalize (isto é treino CORRETO, não erro):
- tiros (VO2/intervalado), fartlek, limiar e tempo mais rápidos que o ritmo de
  prova — SÃO pra ser mais rápidos, por definição;
- qualquer ritmo de qualidade que esteja DENTRO ou perto da capacidade projetada;
- dose de qualidade num atleta cuja projeção mostra que ele aguenta.

Se o plano estiver adequado (o caso mais comum pra atleta em evolução), retorne
lista VAZIA.

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
        goal=None,
        prediction=None,
    ) -> TrainingPlan:
        """Revisa o plano uma única vez por semana (idempotente) e
        persiste os alertas. Falha da IA nunca quebra a entrega.

        `goal`/`prediction` (opcionais): a meta + a projeção de prova do Garmin
        entram como ÂNCORA DE CAPACIDADE — o revisor pega quando o plano
        prescreve ritmo de prova mais rápido do que a projeção sustenta hoje
        (insumo, não decreto: só anota/apara, nunca reescreve o pace)."""

        if (
            plan.source != "runmind"
            or not plan.sessions
            or plan.reviewed
        ):

            return plan

        try:

            concerns = await PlanRealismReviewer._ask(
                runner, plan, goal, prediction,
            )

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
        goal=None,
        prediction=None,
    ) -> list[dict]:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            athlete=PlanRealismReviewer._describe_athlete(runner),
            capacity_section=PlanRealismReviewer._capacity_section(
                goal, prediction,
            ),
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
    def _capacity_section(goal, prediction) -> str:
        """Bloco de CAPACIDADE pro prompt: projeção de prova do Garmin + a meta.
        String vazia (sem seção) quando não há projeção com dado — device sem o
        dado não deve inventar âncora nenhuma."""

        if prediction is None or not getattr(prediction, "has_data", False):

            return ""

        labels = [
            f"{name} ~{value}"
            for name, value in (
                ("5K", prediction.time_5k),
                ("10K", prediction.time_10k),
                ("21K", prediction.time_half),
                ("42K", prediction.time_marathon),
            )
            if value
        ]

        if not labels:

            return ""

        lines = [
            "",
            "CAPACIDADE ATUAL (referência de realismo — ESTIMATIVA do Garmin "
            "pelo VO₂máx+treino, NÃO um decreto):",
            "- Projeção do relógio: " + " · ".join(labels),
        ]

        if goal is not None:

            target = getattr(goal, "target_time", None)

            label = (
                getattr(goal, "race_label", None)
                or getattr(goal, "name", None)
            )

            if label:

                suffix = f" em {target}" if target else ""

                lines.append(f"- Meta do atleta: {label}{suffix}")

        return "\n".join(lines) + "\n"

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
