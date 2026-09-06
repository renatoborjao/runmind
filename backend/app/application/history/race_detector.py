"""Detecta a PROVA recente do atleta — o sinal que faltava pra a análise de carga
não ler o TAPER de uma prova como "carga subindo" nem a reconstrução pós-prova
como sobrecarga nova.

Bug real (Renato/Maurício): prova em 23/08 era o ALVO, o coach afinou pra ela
(cargas caíram: taper), a prova passou e voltamos a dar tração. O DeloadAnalyzer
via só os 4 números de carga — leu o taper como "2 semanas de bloco" e a
reconstrução como sobrecarga → descarga FALSA logo depois da prova.

DUAS fontes, a de PRIMEIRA-MÃO primeiro (não dependemos 100% do Strava):
1. RESULTADO de prova que o COACH já registrou (debrief da prova-alvo) — é o que
   o sistema JÁ SABIA, autoritativo, sem marcação externa. Fonte principal.
2. Fallback: o atleta marcou a corrida como PROVA no Strava
   (`raw.workout_type == 1`) ou o NOME do treino bate um termo de prova — cobre
   quem correu uma prova que não era a alvo (o coach não fez debrief).

Puro/determinístico e best-effort — nenhuma marcação manual do coach.
Ver [[deload_analyzer]], [[race_result_repository]] e
[[feedback_base_historico_sempre]]."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.value_objects.sports import is_run_sport

# Strava: workout_type 1 = "Race" (o atleta marca a atividade como prova)
_STRAVA_RACE_WORKOUT_TYPE = 1

# termos INEQUÍVOCOS de prova no nome (conservador de propósito — "corrida"
# sozinho é todo treino; aqui só o que denota um EVENTO/competição). Sem acento
# e minúsculo (o casamento normaliza).
_RACE_NAME_HINTS = (
    "prova", "race", "run series", "track&field", "track and field",
    "corrida de rua", "meia maratona", "maratona", "half marathon",
    "marathon", "circuito", "desafio", "grand prix", "gp ", "10k ",
    "5k ", "21k", "42k", "night run", "color run",
)

# quão longe atrás procuramos uma prova (cobre taper + reconstrução pós-prova)
_LOOKBACK_WEEKS = 10


@dataclass(slots=True)
class RaceEvent:

    date: date
    name: str
    distance_km: float
    weeks_ago: int


class RaceDetector:

    @staticmethod
    def most_recent(
        activities,
        on_date: date,
        past_results=None,
        lookback_weeks: int = _LOOKBACK_WEEKS,
    ) -> RaceEvent | None:
        """A prova de corrida mais recente em/até `on_date`, dentro da janela.
        Olha PRIMEIRO os resultados que o coach já registrou (`past_results`, do
        RaceResultRepository — a prova que o sistema já SABIA) e, como rede, as
        atividades marcadas como prova. None quando não há prova detectável —
        best-effort, nunca levanta."""

        cutoff = on_date - timedelta(weeks=lookback_weeks)

        best: RaceEvent | None = None

        # 1) FONTE DE PRIMEIRA-MÃO: provas que o coach já debriefou (autoritativo)
        for result in past_results or []:

            try:

                day = RaceDetector._parse_date(result.get("date"))

                if day is None or day > on_date or day < cutoff:

                    continue

                if best is None or day > best.date:

                    best = RaceEvent(
                        date=day,
                        name=str(
                            result.get("race_label")
                            or result.get("name")
                            or "prova"
                        ),
                        distance_km=float(result.get("distance_km") or 0),
                        weeks_ago=(on_date - day).days // 7,
                    )

            except Exception:  # noqa: BLE001 — registro torto não derruba a detecção

                continue

        # 2) REDE: atividades marcadas como prova (Strava workout_type / nome)
        for activity in activities or []:

            try:

                if not is_run_sport(getattr(activity, "sport", None)):

                    continue

                day = RaceDetector._day(getattr(activity, "start_date", None))

                if day is None or day > on_date or day < cutoff:

                    continue

                if not RaceDetector._is_race(activity):

                    continue

                if best is None or day > best.date:

                    best = RaceEvent(
                        date=day,
                        name=str(getattr(activity, "name", "") or ""),
                        distance_km=round(
                            (getattr(activity, "distance", 0) or 0) / 1000, 1
                        ),
                        weeks_ago=(on_date - day).days // 7,
                    )

            except Exception:  # noqa: BLE001 — um registro torto não derruba a detecção

                continue

        return best

    # ------------------------------------------------------------------

    @staticmethod
    def _is_race(activity) -> bool:
        """Prova quando o Strava marca (workout_type==1) OU o nome bate um termo
        inequívoco de prova."""

        raw = getattr(activity, "raw", None)

        if isinstance(raw, dict) and raw.get("workout_type") == _STRAVA_RACE_WORKOUT_TYPE:

            return True

        name = str(getattr(activity, "name", "") or "").lower()

        return any(hint in name for hint in _RACE_NAME_HINTS)

    @staticmethod
    def _day(start_date) -> date | None:

        if isinstance(start_date, datetime):

            return start_date.date()

        if isinstance(start_date, date):

            return start_date

        return None

    @staticmethod
    def _parse_date(value) -> date | None:
        """Data de um resultado de prova (ISO 'YYYY-MM-DD') — None se não parsear."""

        if isinstance(value, datetime):

            return value.date()

        if isinstance(value, date):

            return value

        try:

            return date.fromisoformat(str(value)[:10])

        except (ValueError, TypeError):

            return None
