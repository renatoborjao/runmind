"""Aderência de ESTÍMULO — o atleta não só apareceu no dia, ele EXECUTOU o
que o coach mandou? A aderência "de presença" ([[adherence_analyzer]]) casa
treino×sessão por dia/distância e credita quem correu — mas quem foi no dia do
ritmo e trotou de leve conta igual a quem cumpriu. Aqui a pergunta é o ritmo:
o pace executado caiu na FAIXA-ALVO que o plano prescreveu?

Âncora = `target_pace_min/max` da sessão (o próprio plano declara), não uma
reclassificação frágil. Honestidade dura sobre o TIRO: num treino com blocos
(aquecimento+Nx…+soltura) o pace MÉDIO fica entre o forte e o trote e não
representa o estímulo — esses ficam STRUCTURED (não avaliados por média; medir
de verdade exige os splits, que o arquivo permanente não guarda). Sessão de
plano externo sem pace-alvo (Mauricio) = NO_TARGET (não dá pra cobrar ritmo).

Puro/sem IO — recebe planos e histórico já carregados."""

from dataclasses import dataclass, field
from datetime import date

from app.application.history.adherence_analyzer import (
    LOOKBACK_WEEKS,
    AdherenceAnalyzer,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.clock import today_local
from app.domain.entities.activity import Activity
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import INTERVAL, REPEAT

_RUNNING_KINDS = {"run", "walk", "run_walk"}

# folga (s/km) além da faixa prescrita antes de cravar desvio — a faixa já é
# um alvo, isto é a margem humana (esteira, GPS, relevo, subir a rua)
PACE_TOLERANCE_SEC = 20

# nomes que denunciam treino de BLOCOS (tiro), onde a média não representa o
# estímulo. Um treino batizado assim não é julgado pela média mesmo que os
# passos estruturados não tenham sido gravados — evita falso-negativo (acusar
# de 'pegou leve' quem correu os tiros certos e diluiu a média no trote).
# 'tempo'/'limiar' contínuos ficam de FORA (são esforço sustentado, a média
# vale); só entram os que alternam forte/fraco.
_INTERVAL_NAME_CUES = (
    "interval", "tiro", "fartlek", "vo2", "vo₂", "sprint",
    "série", "serie", "repeti",
)

# vereditos por sessão avaliada
ON_TARGET = "ON_TARGET"    # correu na faixa (± tolerância): executou o estímulo
TOO_SLOW = "TOO_SLOW"      # bem mais lento que o prescrito: pegou leve
TOO_FAST = "TOO_FAST"      # bem mais rápido: forçou além (fura o fácil/descarga)
STRUCTURED = "STRUCTURED"  # tem tiros e NÃO há veredito bloco-a-bloco (sem splits)
NO_TARGET = "NO_TARGET"    # sessão sem pace-alvo: não dá pra cobrar ritmo

# tiros medidos bloco-a-bloco (splits do Garmin, via StimulusResultStore)
INTERVAL_HIT = "INTERVAL_HIT"          # executou os tiros no ritmo
INTERVAL_PARTIAL = "INTERVAL_PARTIAL"  # parte dos tiros no alvo
INTERVAL_MISS = "INTERVAL_MISS"        # furou os tiros (fora do ritmo/não fez)

# veredito de tiro (StimulusResultStore) -> veredito da sessão
_INTERVAL_VERDICT = {
    "HIT": INTERVAL_HIT,
    "PARTIAL": INTERVAL_PARTIAL,
    "MISS": INTERVAL_MISS,
}

# entram na conta do rate (sessões que dá pra julgar o estímulo)
_EVALUATED = {
    ON_TARGET, TOO_SLOW, TOO_FAST,
    INTERVAL_HIT, INTERVAL_PARTIAL, INTERVAL_MISS,
}

# contam como "executou o estímulo" (numerador do rate)
_ON_TARGET_VERDICTS = {ON_TARGET, INTERVAL_HIT}


@dataclass(slots=True)
class SessionStimulus:
    """Uma sessão que teve treino casado, confrontada no RITMO."""

    week_start: date
    day: str
    workout_type: str
    verdict: str
    target: str | None      # "6:20–6:45"
    executed: str | None    # "6:38"
    delta_sec: int | None   # executado − limite mais próximo (+lento / −rápido)
    detail: str | None = None  # tiros: "4/5 no alvo"


@dataclass(slots=True)
class StimulusReport:
    """Aderência de ritmo no período. `rate` = fração das sessões AVALIÁVEIS
    (contínuas com pace-alvo) em que o atleta correu na faixa. Tiros e sessões
    sem alvo saem da conta do rate (viram observação à parte)."""

    sessions: list[SessionStimulus] = field(default_factory=list)

    @property
    def evaluated(self) -> list[SessionStimulus]:

        return [s for s in self.sessions if s.verdict in _EVALUATED]

    @property
    def on_target(self) -> list[SessionStimulus]:

        return [s for s in self.sessions if s.verdict in _ON_TARGET_VERDICTS]

    @property
    def too_slow(self) -> list[SessionStimulus]:

        return [s for s in self.sessions if s.verdict == TOO_SLOW]

    @property
    def too_fast(self) -> list[SessionStimulus]:

        return [s for s in self.sessions if s.verdict == TOO_FAST]

    @property
    def structured(self) -> list[SessionStimulus]:

        return [s for s in self.sessions if s.verdict == STRUCTURED]

    @property
    def interval_hit(self) -> list[SessionStimulus]:

        return [s for s in self.sessions if s.verdict == INTERVAL_HIT]

    @property
    def interval_missed(self) -> list[SessionStimulus]:
        """Tiros furados (fora do ritmo ou não feitos) — o caso que a média
        escondia e agora os splits revelam."""

        return [
            s
            for s in self.sessions
            if s.verdict in (INTERVAL_MISS, INTERVAL_PARTIAL)
        ]

    @property
    def rate(self) -> float | None:

        evaluated = self.evaluated

        return len(self.on_target) / len(evaluated) if evaluated else None


class StimulusAdherence:

    @staticmethod
    def analyze(
        plans: list[TrainingPlan],
        history: TrainingHistory,
        until_week: date,
        weeks: int = LOOKBACK_WEEKS,
        reference_date: date | None = None,
        interval_results: dict[int, dict] | None = None,
    ) -> StimulusReport:
        """`interval_results`: mapa activity_id -> veredito de tiro bloco-a-bloco
        (do StimulusResultStore, gravado no pós-treino). Quando presente pra um
        treino de tiro, o veredito real entra no lugar de 'não medido'. Mantido
        PURO: o report carrega o store e injeta aqui."""

        today = reference_date or today_local()

        interval_results = interval_results or {}

        window = AdherenceAnalyzer._plans_in_window(plans, until_week, weeks)

        by_id = {activity.id: activity for activity in history.activities}

        sessions: list[SessionStimulus] = []

        for plan in window:

            assignments = WeeklyPlanMatcher._assign_week(
                plan,
                history.activities,
            )

            for activity_id, session in assignments.items():

                if session is None or session.kind not in _RUNNING_KINDS:

                    continue

                if plan.session_date(session) > today:

                    continue

                activity = by_id.get(activity_id)

                if activity is None:

                    continue

                sessions.append(
                    StimulusAdherence._evaluate(
                        plan, session, activity,
                        interval_results.get(activity_id),
                    )
                )

        sessions.sort(key=lambda s: (s.week_start, s.day))

        return StimulusReport(sessions=sessions)

    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate(
        plan: TrainingPlan,
        session: PlannedSession,
        activity: Activity,
        interval_result: dict | None = None,
    ) -> SessionStimulus:

        executed_sec = StimulusAdherence._executed_pace_sec(activity)

        target_min = PaceFormatter.to_minutes(session.target_pace_min)

        target_max = PaceFormatter.to_minutes(session.target_pace_max)

        executed_str = (
            PaceFormatter.format(executed_sec / 60)
            if executed_sec is not None
            else None
        )

        target_str = (
            f"{session.target_pace_min}–{session.target_pace_max}"
            if target_min is not None and target_max is not None
            else None
        )

        base = {
            "week_start": plan.week_start,
            "day": session.day,
            "workout_type": session.workout_type or "—",
            "target": target_str,
            "executed": executed_str,
        }

        # tiro: o pace médio não representa o estímulo
        if StimulusAdherence._is_structured(session):

            # há veredito bloco-a-bloco (splits do Garmin)? usa a verdade dos
            # tiros no lugar de 'não medido'
            if interval_result and interval_result.get("verdict") in _INTERVAL_VERDICT:

                return SessionStimulus(
                    verdict=_INTERVAL_VERDICT[interval_result["verdict"]],
                    delta_sec=None,
                    detail=(
                        f"{interval_result.get('on_target', 0)}/"
                        f"{interval_result.get('total', 0)} no alvo"
                    ),
                    **base,
                )

            return SessionStimulus(verdict=STRUCTURED, delta_sec=None, **base)

        # sem alvo de pace (plano externo) ou treino sem ritmo mensurável
        if target_min is None or target_max is None or executed_sec is None:

            return SessionStimulus(verdict=NO_TARGET, delta_sec=None, **base)

        # pace_min é o mais RÁPIDO (menor s/km); pace_max o mais LENTO
        fastest = target_min * 60

        slowest = target_max * 60

        if executed_sec > slowest + PACE_TOLERANCE_SEC:

            return SessionStimulus(
                verdict=TOO_SLOW,
                delta_sec=round(executed_sec - slowest),
                **base,
            )

        if executed_sec < fastest - PACE_TOLERANCE_SEC:

            return SessionStimulus(
                verdict=TOO_FAST,
                delta_sec=round(executed_sec - fastest),
                **base,
            )

        return SessionStimulus(verdict=ON_TARGET, delta_sec=0, **base)

    @staticmethod
    def _executed_pace_sec(activity: Activity) -> float | None:
        """Pace médio real em s/km. None quando não dá pra medir (distância ou
        tempo zerado no registro reduzido)."""

        if activity.distance <= 0 or activity.moving_time <= 0:

            return None

        return activity.moving_time / (activity.distance / 1000)

    @staticmethod
    def _is_structured(session: PlannedSession) -> bool:
        """Treino com blocos de esforço (tiros) — média não mede. Denuncia a
        estrutura por DUAS vias: os passos (um `repeat`/`interval`) OU o nome
        do treino (nem toda sessão de tiro teve os passos gravados; o nome
        'Intervalado VO2' já basta pra não julgar pela média)."""

        if any(
            step.kind in (REPEAT, INTERVAL)
            for step in (session.steps or [])
        ):

            return True

        name = (session.workout_type or "").lower()

        return any(cue in name for cue in _INTERVAL_NAME_CUES)
