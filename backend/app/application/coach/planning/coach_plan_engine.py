import json
from datetime import date

from google.genai import types

from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import parse_steps
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# Pro pensa (thinking) e isso conta no orçamento de saída + é cobrado como
# output. Damos um teto de thinking EXPLÍCITO (não dinâmico, que gastaria ~8k)
# e um max_output com folga pra caber thinking + o JSON do plano — senão o
# thinking come o orçamento e volta vazio (bug conhecido).
THINKING_BUDGET = 1024

# Folga generosa: o JSON do plano (3-5 sessões com steps aninhados) + o
# thinking do Pro precisam caber sem CORTE — JSON cortado é a principal
# causa de quebra e do retry PAGO. Só paga o que gera, não o teto; então a
# folga é de graça e derruba os retries.
MAX_OUTPUT_TOKENS = 6000

VALID_DAYS = set(WEEKDAYS.values())

# só planejamos corrida/caminhada; musculação, descanso, bike etc. NÃO são
# nossos — o atleta cuida disso. Se a IA devolver, a gente descarta.
RUNNING_KINDS = {"run", "walk", "run_walk"}

PROMPT_TEMPLATE = """Você é um treinador de corrida experiente montando o plano \
da PRÓXIMA SEMANA para um atleta específico. O plano tem que ser REAL e VIVO:
segue a evolução, os limites e a rotina que já funcionam para ELE — nada de
fórmula genérica nem de inflar volume.

RETRATO REAL DO ATLETA (dados do histórico dele — use só isto, não invente):
{context}

REGRAS:
- O plano é SÓ de corrida/caminhada. NÃO prescreva musculação, descanso, bike
  ou qualquer outra atividade — isso não é seu (o atleta cuida por conta).
  Apenas as sessões de corrida/caminhada nos dias de corrida dele.
- Respeite a FREQUÊNCIA de corrida que funciona para ele (não adicione dias só
  para "encher"). Se ele responde bem a N corridas por semana, mantenha N.
- TREINE RUMO À META — não faça manutenção. O plano deve EVOLUIR o atleta em
  direção ao objetivo, não sentar no volume/ritmo médio atual dele. Quando ele
  vem consistente, dê um passo a mais na semana: suba um pouco o volume
  (progressão gradual, tipicamente +5 a +10%) OU aprofunde a qualidade (ritmo
  mais perto do alvo, série um pouco maior) — sempre construindo o que a META
  exige.
- MAS COM CRITÉRIO, segurança primeiro: um PASSO por semana, nunca um salto
  grande (risco de lesão). Respeite a capacidade real e a aderência — se ele
  vem cumprindo pouco, segure ou recue; respeite a fase do ciclo (longe da
  prova = construir base/volume; perto = afiar qualidade; véspera = poupar).
  Nunca prescreva estímulo que o nível dele ainda não comporta.
- 1º plano (sem aderência registrada): comece perto do volume atual, MAS já com
  leve inclinação de evolução e a ESTRUTURA que a meta pede (ex.: se a meta é
  de tempo, inclua um treino no ritmo-alvo). O atleta veio pra MELHORAR, não
  pra manter.
- Cada corrida com um PROPÓSITO distinto (velocidade, base/rodagem, longão,
  regenerativo...) e faixa de pace ancorada na META dele.
- LONGÃO só quando faz sentido: um "longão" é o treino MAIS LONGO da semana E
  claramente ACIMA da rodagem típica dele. Se o atleta ainda corre pouco (ex.:
  rodagem típica/maior treino ~5 km), NÃO rotule nenhuma corrida de "Longão" —
  chame de rodagem/base. O longão só aparece quando o volume evolui e existe
  uma corrida realmente mais longa. NUNCA dê o nome "Longão" a uma distância
  igual (ou menor) à rodagem comum do atleta.
- "structure" é uma LISTA de passos CLAROS e COMPLETOS, em linguagem simples
  que qualquer corredor entende. Detalhe de verdade: aquecimento (distância +
  pace), a parte principal (séries/distâncias/repetições/pace/recuperação
  EXPLÍCITOS), o desaquecimento e uma dica prática. Um passo por item.
- "steps" é a MESMA prescrição em formato ESTRUTURADO (pra virar treino
  guiado no relógio). Use os blocos reais do treino, na ordem:
    * kind: "warmup" | "run" | "interval" | "recovery" | "rest" | "cooldown"
      | "repeat"
    * fim do bloco: "distance_m" OU "distance_km" OU "duration_min" (escolha
      o que o treino pede; tiro costuma ser distance_m, rodagem distance_km,
      recuperação pode ser duration_min)
    * alvo: "pace_min"/"pace_max" (mm:ss por km; min = mais rápido) quando
      houver ritmo; recuperação/aquecimento podem ir sem alvo
    * "repeat" agrupa o que se repete: {{"kind":"repeat","reps":6,"steps":[
      bloco de esforço, bloco de recuperação]}}
  Monte o treino que fizer sentido pra evolução dele — contínuo, intervalado,
  tempo, progressivo, fartlek: o formato aceita todos.
- Respeite lesões/limitações que aparecerem no retrato.
- AVERSÕES A TIPO DE TREINO: se o retrato disser que o atleta não gosta de um
  tipo de treino, NÃO ignore — mas também NÃO jogue fora o estímulo que ele
  precisa pra meta. Distinga o motivo:
    * Gosto/tédio (ex.: "acha tiro na pista chato") -> MANTENHA o estímulo
      fisiológico e troque só a FORMA (ex.: fartlek na rua no lugar de
      intervalado na pista; progressivo no lugar de tempo em ritmo fixo).
    * Restrição física/dor (ex.: "subida incomoda o joelho") -> ADAPTE ou
      REMOVA de verdade aquele estímulo e compense com outro seguro.
  Explique a troca no "purpose" da sessão, pra ele ver que você ouviu e por
  que o objetivo foi mantido.

Responda APENAS com JSON:
{{"weekly_objective": "objetivo/foco curto da semana",
  "sessions": [
    {{"day": "Tuesday", "kind": "run", "workout_type": "Velocidade",
      "distance_km": 9.0, "pace_min": "4:45", "pace_max": "4:50",
      "structure": [
        "Aquecimento: 2 km bem leve (6:30-7:00/km) + 3 educativos curtos",
        "Série: 6x 800m no pace 4:45-4:50/km",
        "Recuperação: 400m de trote leve entre cada tiro",
        "Desaquecimento: 1,5 km leve soltando as pernas",
        "Dica: comece o 1º tiro mais controlado pra não estourar no fim"
      ],
      "steps": [
        {{"kind": "warmup", "distance_km": 2, "pace_min": "6:30", "pace_max": "7:00"}},
        {{"kind": "repeat", "reps": 6, "steps": [
          {{"kind": "interval", "distance_m": 800, "pace_min": "4:45", "pace_max": "4:50"}},
          {{"kind": "recovery", "distance_m": 400}}
        ]}},
        {{"kind": "cooldown", "distance_km": 1.5, "pace_min": "6:30", "pace_max": "7:00"}}
      ],
      "purpose": "aumentar o ritmo de prova"}}
  ]}}

Cada sessão é uma corrida/caminhada com distance_km, paces, structure (texto),
steps (estruturado) e purpose. kind: "run" (corrida) ou "walk"/"run_walk"
(caminhada/corrida-caminhada, iniciante). Dias em inglês (Monday..Sunday).
"""


class CoachPlanEngine:
    """IA-treinadora: gera o plano da semana a partir do retrato real do
    atleta. Se falhar, o chamador cai no motor determinístico (fallback)."""

    @staticmethod
    async def generate(
        runner_name: str,
        objective: str,
        week_start: date,
        context: str,
    ) -> TrainingPlan:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(context=context)

        # generate_json re-gera se o JSON do plano vier torto (blindagem) —
        # o plano é core; não pode cair no determinístico por escorregada do
        # modelo. Só cai no fallback (AIPlanService) se TODAS as tentativas
        # falharem, aí levanta pra ele.
        plan = await generate_json(
            model=settings.gemini_coach_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=THINKING_BUDGET,
                ),
            ),
            parse=lambda raw: CoachPlanEngine._parse_plan(
                raw, runner_name, objective, week_start,
            ),
        )

        if plan is None:

            raise ValueError("plano da IA inválido após as tentativas")

        return plan

    @staticmethod
    def _parse_plan(
        raw: str,
        runner_name: str,
        objective: str,
        week_start: date,
    ) -> TrainingPlan | None:
        """Wrapper de _to_plan pra o generate_json: devolve None em qualquer
        problema (JSON torto, sem corridas) em vez de levantar, pra re-gerar."""

        try:

            return CoachPlanEngine._to_plan(
                raw, runner_name, objective, week_start,
            )

        except (ValueError, json.JSONDecodeError, TypeError):

            return None

    @staticmethod
    def _to_plan(
        raw: str,
        runner_name: str,
        objective: str,
        week_start: date,
    ) -> TrainingPlan:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError) as e:

            raise ValueError(f"JSON do plano inválido: {e}")

        if not isinstance(data, dict):

            raise ValueError("plano da IA não é um objeto")

        sessions = CoachPlanEngine._parse_sessions(
            data.get("sessions", []),
        )

        if not any(s.kind == "run" for s in sessions):

            raise ValueError("plano da IA sem corridas")

        running_days = [s.day for s in sessions if s.kind == "run"]

        weekly_volume = round(
            sum(s.planned_distance_km or 0 for s in sessions),
            1,
        )

        return TrainingPlan(
            athlete_name=runner_name,
            objective=objective,
            phase="IA",
            weekly_volume=weekly_volume,
            running_days=running_days,
            week_start=week_start,
            sessions=sessions,
            weekly_objective=str(data.get("weekly_objective", "")).strip(),
        )

    @staticmethod
    def _parse_sessions(raw_sessions) -> list[PlannedSession]:

        if not isinstance(raw_sessions, list):

            return []

        sessions = []

        for item in raw_sessions:

            if not isinstance(item, dict):

                continue

            day = item.get("day")

            if day not in VALID_DAYS:

                continue

            kind = item.get("kind", "run")

            # descarta musculação/descanso/bike — não planejamos isso
            if kind not in RUNNING_KINDS:

                continue

            distance = item.get("distance_km")

            if not isinstance(distance, (int, float)) or distance <= 0:

                distance = None

            sessions.append(
                PlannedSession(
                    day=day,
                    workout_type=(
                        item.get("workout_type")
                        or CoachPlanEngine._default_type(kind)
                    ),
                    objective=str(item.get("purpose", "")).strip(),
                    planned_distance_km=(
                        round(float(distance), 1)
                        if distance is not None
                        else None
                    ),
                    planned_duration_minutes=None,
                    target_pace_min=CoachPlanEngine._pace(item.get("pace_min")),
                    target_pace_max=CoachPlanEngine._pace(item.get("pace_max")),
                    kind=kind,
                    structure=CoachPlanEngine._structure(
                        item.get("structure"),
                    ),
                    purpose=str(item.get("purpose", "")).strip(),
                    steps=parse_steps(item.get("steps")),
                )
            )

        return sessions

    @staticmethod
    def _structure(value) -> str:
        """Estrutura vem como lista de passos (preferido) ou string; guarda
        um passo por linha pra o formatter renderizar cada um."""

        if isinstance(value, list):

            return "\n".join(
                str(step).strip() for step in value if str(step).strip()
            )

        return str(value or "").strip()

    @staticmethod
    def _default_type(kind: str) -> str:

        return {
            "walk": "Caminhada",
            "run_walk": "Corrida-caminhada",
        }.get(kind, "Corrida")

    @staticmethod
    def _pace(value) -> str | None:

        if not value:

            return None

        return str(value).strip()
