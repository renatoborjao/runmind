"""O coach DECIDE a conduta quando, na VÉSPERA de um treino exigente, o corpo do
atleta pede freio. A IA-treinadora pesa meta, aderência e evolução e escolhe:
ALIVIAR, REMANEJAR ou MANTER (o corpo aguenta / a meta pede). Devolve a decisão
estruturada + a mensagem-PROPOSTA pro atleta.

Por que véspera e por que proposta: um dia de descanso pode restaurar o atleta —
quem sente se ele chegou inteiro é ele, o que o Garmin não vê 100%. Então o
coach lidera pelos dados MAS propõe, e o atleta confirma pelo que sente (o 'sim'
aplica pelo ProposalFlow). Espelha o MoveSkipEngine.

Se a IA cair, devolve None — o silêncio é a degradação segura (não propõe nada
no escuro)."""

import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date

from google.genai import types

from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS, weekday_label, weekday_name
from app.domain.entities.body_reading import BodyReading
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

VALID_DAYS = set(WEEKDAYS.values())

MAX_OUTPUT_TOKENS = 600

_RUNNING_KINDS = {"run", "walk", "run_walk"}

# pistas de treino EXIGENTE (intenso ou longo) — o que faz sentido aliviar
# quando o corpo pede recuperação
_DEMANDING_CUES = (
    "veloc", "tiro", "interval", "limiar", "threshold", "ritmo", "tempo",
    "progress", "fartlek", "vo2", "forte", "long",  # longo/longao/longão
)

PROMPT_TEMPLATE = """Você é o TREINADOR de corrida do Ritmind, cuidando do \
atleta {runner_name}. AMANHÃ ele tem um treino EXIGENTE e o corpo dele, HOJE \
(véspera), está pedindo recuperação. Você decide a conduta pelos dados — mas \
como falta um dia, um descanso hoje pode restaurá-lo; então você PROPÕE e ele \
confirma pelo que sentir.

Hoje é {today}. Meta: {goal}.

O CORPO dele agora (carga à luz da recuperação):
{body}

PLANO DESTA SEMANA (dias de corrida):
{sessions}

O treino exigente de AMANHÃ é: {target} ({target_day}).

Decida a melhor conduta pra ESSE treino, pesando a meta e que recuperar agora \
é o que SUSTENTA a evolução (não corte por cortar, mas não empilhe carga num \
corpo que não assimila):
- "ease": aliviar o treino. Dê "ease_km" (distância menor, leve) — vira rodagem \
leve.
- "move": remanejar pra um dia LIVRE mais pra frente da semana. Dê \
"target_day" (inglês), que NÃO pode ter treino planejado.
- "keep": manter (o corpo aguenta / a meta pede) — sem mudança.

A "message" é uma PROPOSTA curta de WhatsApp (sem markdown): diz o que você viu \
no corpo, propõe a mudança pro treino de amanhã e POR QUÊ (recuperação/\
evolução), e — por ser véspera — reconhece que se ele descansar hoje e amanhã \
acordar inteiro, pode manter. TERMINA deixando claro que basta ele confirmar \
que você ajusta (ou dizer que está pronto que você mantém). Tom de treinador \
que cuida. No "keep", a message pode ficar vazia.

Responda APENAS JSON:
{{"action": "ease", "ease_km": 6, "message": "..."}}
{{"action": "move", "target_day": "Friday", "message": "..."}}
{{"action": "keep", "message": ""}}
"""

# Variante DIA-DO-TREINO: a proposta sai na manhã do próprio treino (gatilho do
# despertar), com o dado FRESCO da noite. Sem a lógica de "véspera/descanso pode
# restaurar" — aqui o dado é de agora e a decisão é pra hoje.
PROMPT_TEMPLATE_TODAY = """Você é o TREINADOR de corrida do Ritmind, cuidando do \
atleta {runner_name}. HOJE ele tem um treino EXIGENTE e o corpo dele, NESTA \
MANHÃ (dado fresco do sono/recuperação da noite), está pedindo recuperação. \
Você decide a conduta pelos dados — mas quem sente se ele acordou inteiro é ele; \
então você PROPÕE e ele confirma.

Hoje é {today}. Meta: {goal}.

O CORPO dele agora (carga à luz da recuperação):
{body}

PLANO DESTA SEMANA (dias de corrida):
{sessions}

O treino exigente de HOJE é: {target} ({target_day}).

Decida a melhor conduta pra ESSE treino de hoje, pesando a meta e que recuperar \
agora é o que SUSTENTA a evolução (não corte por cortar, mas não empilhe carga \
num corpo que não assimila):
- "ease": aliviar o treino de HOJE. Dê "ease_km" (distância menor, leve) — vira \
rodagem leve.
- "move": remanejar pra um dia LIVRE mais pra frente da semana. Dê \
"target_day" (inglês), que NÃO pode ter treino planejado.
- "keep": manter (o corpo aguenta / a meta pede) — sem mudança.

A "message" é uma PROPOSTA curta de WhatsApp (sem markdown): diz o que você viu \
no corpo dele HOJE, propõe a mudança pro treino de hoje e POR QUÊ (recuperação/\
evolução). TERMINA deixando claro que basta ele confirmar que você ajusta (ou \
dizer que está pronto que você mantém). Tom de treinador que cuida. No "keep", a \
message pode ficar vazia.

Responda APENAS JSON:
{{"action": "ease", "ease_km": 6, "message": "..."}}
{{"action": "move", "target_day": "Friday", "message": "..."}}
{{"action": "keep", "message": ""}}
"""


@dataclass(slots=True)
class BodyConductDecision:

    action: str            # "ease" | "move" | "keep"

    operations: list[dict]  # o que aplicar no plano ([] no keep)

    message: str           # informe pro atleta ("" no keep)


class BodyConductEngine:

    @staticmethod
    def next_demanding_session(
        plan: TrainingPlan,
        today: date,
        done_days: set[str] | None = None,
    ) -> PlannedSession | None:
        """A próxima sessão exigente ainda por vir (data > hoje, não cumprida):
        a primeira intensa/longa por tipo; se nenhuma casa por rótulo, o maior
        longão futuro. None se não há corrida exigente à frente."""

        done = {d.lower() for d in (done_days or set())}

        upcoming = [
            s
            for s in sorted(plan.sessions, key=plan.session_date)
            if plan.session_date(s) > today
            and s.day.lower() not in done
            and s.kind in _RUNNING_KINDS
        ]

        for session in upcoming:

            if BodyConductEngine._is_demanding(session):

                return session

        # nenhuma rotulada como exigente: o maior treino futuro (o longão)
        runs = [s for s in upcoming if s.planned_distance_km]

        if runs:

            longest = max(runs, key=lambda s: s.planned_distance_km)

            # só vale aliviar se for de fato um treino de peso (>= 10km)
            if (longest.planned_distance_km or 0) >= 10:

                return longest

        return None

    @staticmethod
    def todays_demanding_session(
        plan: TrainingPlan,
        today: date,
        done_days: set[str] | None = None,
    ) -> PlannedSession | None:
        """A sessão exigente de HOJE ainda não cumprida (data == hoje) — pro
        ajuste no dia do treino (gatilho do despertar). Intensa/longa por
        rótulo; senão, longão de hoje (>= 10km). None se hoje não há treino
        exigente pendente."""

        done = {d.lower() for d in (done_days or set())}

        todays = [
            s
            for s in plan.sessions
            if plan.session_date(s) == today
            and s.day.lower() not in done
            and s.kind in _RUNNING_KINDS
        ]

        for session in todays:

            if BodyConductEngine._is_demanding(session):

                return session

        for session in todays:

            if (session.planned_distance_km or 0) >= 10:

                return session

        return None

    @staticmethod
    async def decide(
        runner: RunnerProfile,
        plan: TrainingPlan,
        reading: BodyReading,
        session: PlannedSession,
        today: date,
        goal: str,
        when: str = "eve",
    ) -> BodyConductDecision | None:

        settings = get_settings()

        # "today" = proposta na manhã do treino (dado fresco); "eve" = véspera
        template = (
            PROMPT_TEMPLATE_TODAY if when == "today" else PROMPT_TEMPLATE
        )

        prompt = template.format(
            runner_name=runner.name,
            today=(
                f"{weekday_label(weekday_name(today))}, "
                f"{today.strftime('%d/%m/%Y')}"
            ),
            goal=goal,
            body=BodyConductEngine._render_body(reading),
            sessions=BodyConductEngine._render_sessions(plan),
            target=session.workout_type,
            target_day=weekday_label(session.day),
        )

        return await generate_json(
            model=settings.gemini_coach_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=lambda raw: BodyConductEngine._parse(raw, plan, session),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def is_demanding(session: PlannedSession) -> bool:
        """Fonte ÚNICA de 'treino exigente' (intenso ou longo). Público pra o
        vigia de prontidão reusar o mesmo critério do ajuste de corpo."""

        return BodyConductEngine._is_demanding(session)

    @staticmethod
    def _is_demanding(session: PlannedSession) -> bool:

        norm = BodyConductEngine._normalize(session.workout_type)

        return any(cue in norm for cue in _DEMANDING_CUES)

    @staticmethod
    def _render_body(reading: BodyReading) -> str:

        rec = reading.recovery

        parts = [f"estado {reading.body_state}"]

        if reading.limiter:

            parts.append(f"limitador: {reading.limiter}")

        if reading.load.acwr is not None:

            parts.append(f"ACWR {reading.load.acwr:.2f} ({reading.load.status})")

        if rec.hrv_recent is not None:

            parts.append(f"HRV {rec.hrv_recent:.0f} ({rec.hrv_direction})")

        return "; ".join(parts) + "."

    @staticmethod
    def _render_sessions(plan: TrainingPlan) -> str:

        lines = []

        for session in plan.sessions:

            if session.kind not in _RUNNING_KINDS:

                continue

            distance = (
                f"{session.planned_distance_km:.0f}km"
                if session.planned_distance_km
                else "s/ distância"
            )

            lines.append(
                f"- {weekday_label(session.day)} ({session.day}): "
                f"{session.workout_type}, {distance}"
            )

        return "\n".join(lines) or "(sem sessões de corrida)"

    @staticmethod
    def _parse(
        raw: str,
        plan: TrainingPlan,
        session: PlannedSession,
    ) -> BodyConductDecision | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict):

            return None

        action = data.get("action")

        message = str(data.get("message", "")).strip()

        if action == "keep":

            return BodyConductDecision(action="keep", operations=[], message="")

        if action == "ease":

            if not message:

                return None

            return BodyConductDecision(
                action="ease",
                operations=BodyConductEngine._ease_ops(
                    session, data.get("ease_km")
                ),
                message=message,
            )

        if action == "move":

            target_day = data.get("target_day")

            if (
                not message
                or target_day not in VALID_DAYS
                or target_day.lower() == session.day.lower()
                or plan.find_session_by_day(target_day) is not None
            ):

                return None

            return BodyConductDecision(
                action="move",
                operations=BodyConductEngine._move_ops(session, target_day),
                message=message,
            )

        return None

    @staticmethod
    def _ease_ops(session: PlannedSession, ease_km) -> list[dict]:
        """Alivia a sessão: vira uma rodagem leve, mais curta, sem estrutura
        puxada. Distância da IA validada; sem número válido cai em ~60%."""

        eased = asdict(session)

        original = session.planned_distance_km

        km = None

        try:

            km = float(ease_km)

        except (TypeError, ValueError):

            km = None

        # só aceita um alívio de verdade: menor que o original e positivo
        if not km or km <= 0 or (original and km >= original):

            km = round(original * 0.6, 0) if original else None

        eased["workout_type"] = "Rodagem leve"

        eased["planned_distance_km"] = km

        eased["target_pace_min"] = None

        eased["target_pace_max"] = None

        eased["steps"] = []

        eased["structure"] = ""

        eased["intervals"] = None

        eased["adjusted"] = True

        eased["adjustment_reason"] = "corpo pedindo recuperação"

        eased.pop("garmin", None)

        return [{"action": "replace", "day": session.day, "session": eased}]

    @staticmethod
    def _move_ops(session: PlannedSession, target_day: str) -> list[dict]:

        moved = asdict(session)

        moved["day"] = target_day

        moved["adjusted"] = True

        moved["adjustment_reason"] = "remanejado: corpo pedindo recuperação"

        moved.pop("garmin", None)

        return [
            {"action": "drop", "day": session.day},
            {"action": "replace", "day": target_day, "session": moved},
        ]

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = (text or "").lower().strip()

        return "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )
