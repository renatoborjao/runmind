"""PERCEPÇÃO do atleta — a terceira perna do coach (evolução × objetivo ×
percepção). Antes só entrava quando o atleta respondia um NÚMERO à pergunta
pós-treino (que só saía em treino exigente): em 28 dias, 5 de 6 atletas tinham
ZERO registros (27/09). Agora três portas gravam no MESMO lugar
(SessionRpeRepository), cada uma com a sua fonte:

- "relógio": a autoavaliação do Garmin (esforço 1-10 + sensação) que o atleta
  marca ao salvar a corrida — vem de graça, em TODO treino, sem perguntar;
- "resposta": o número respondido à pergunta pós-treino (RpeFlow);
- "conversa": o que ele conta num papo qualquer ("perna pesada hoje", "voei no
  longão") — o cérebro do chat lê e devolve estruturado.

Uma percepção por treino; a conversa ENRIQUECE a do relógio (mantém o número se
ele não deu outro, junta as palavras dele). Best-effort: nunca derruba nada."""

from datetime import date, timedelta

from app.core.clock import now_local, today_local
from app.domain.entities.session_rpe import SessionRpe
from app.infrastructure.persistence.session_rpe_repository import (
    SessionRpeRepository,
)

# sensação do Garmin (directWorkoutFeel, 0-100 em passos de 25) — fonte ÚNICA
# (a análise do treino lê daqui também)
WATCH_FEEL_WORDS = {
    0: "muito cansado",
    25: "cansado",
    50: "normal",
    75: "bem",
    100: "forte",
}

# a conversa só grava percepção de treino recente (relato de semanas atrás
# não é mais "como foi")
_CHAT_MAX_AGE_DAYS = 7

_NOTE_CHARS = 160


class PerceptionRecorder:

    @staticmethod
    def from_watch(profile: str, activity) -> bool:
        """Grava a autoavaliação do relógio, se o atleta marcou. True = já
        temos a percepção deste treino (não precisa perguntar)."""

        from app.application.history.weekly_buckets import activity_date

        try:

            metrics = (getattr(activity, "raw", None) or {}).get(
                "_garmin_metrics"
            ) or {}

            raw_rpe = metrics.get("workout_rpe")

            if raw_rpe is None:

                return False

            # Garmin guarda o esforço 1-10 multiplicado por 10
            rpe = max(0, min(10, round(float(raw_rpe) / 10)))

            feel = PerceptionRecorder._watch_feel(metrics.get("workout_feel"))

            duration = round((activity.moving_time or 0) / 60, 1)

            SessionRpeRepository().record(
                profile,
                SessionRpe(
                    activity_id=int(activity.id),
                    day=activity_date(activity).isoformat(),
                    duration_min=duration,
                    rpe=rpe,
                    srpe=round(duration * rpe, 1),
                    at=now_local().isoformat(),
                    feel=f"sentiu-se {feel}" if feel else None,
                    source="relógio",
                ),
            )

            return True

        except Exception as e:

            print(f"Percepção do relógio falhou p/ '{profile}': {e}")

            return False

    @staticmethod
    def from_chat(profile: str, perception: dict | None) -> bool:
        """Grava o que o atleta contou na conversa sobre como se sentiu num
        treino recente. `perception` = {"day": iso, "rpe": 0-10|None,
        "feel": str|None} vindo do cérebro."""

        if not perception:

            return False

        try:

            day = date.fromisoformat(str(perception.get("day") or "")[:10])

        except ValueError:

            return False

        today = today_local()

        if day > today or day < today - timedelta(days=_CHAT_MAX_AGE_DAYS):

            return False

        rpe = perception.get("rpe")

        try:

            rpe = None if rpe is None else max(0, min(10, int(round(float(rpe)))))

        except (TypeError, ValueError):

            rpe = None

        feel = " ".join(str(perception.get("feel") or "").split())[:_NOTE_CHARS]

        try:

            activity = PerceptionRecorder._run_on(profile, day)

            if activity is None:

                return False

            repo = SessionRpeRepository()

            existing = next(
                (
                    s for s in repo.load_sessions(profile)
                    if s.activity_id == int(activity.id)
                ),
                None,
            )

            if rpe is None and existing is None:

                # sem número nem registro anterior não há como compor o sRPE
                return False

            final_rpe = rpe if rpe is not None else existing.rpe

            duration = round((activity.moving_time or 0) / 60, 1)

            notes = [
                n for n in (
                    getattr(existing, "note", None) if existing else None,
                    feel or None,
                ) if n
            ]

            repo.record(
                profile,
                SessionRpe(
                    activity_id=int(activity.id),
                    day=day.isoformat(),
                    duration_min=duration,
                    rpe=final_rpe,
                    srpe=round(duration * final_rpe, 1),
                    at=now_local().isoformat(),
                    feel=getattr(existing, "feel", None) if existing else None,
                    note=" | ".join(dict.fromkeys(notes))[:_NOTE_CHARS * 2] or None,
                    source=(
                        "conversa"
                        if existing is None or rpe is not None
                        else existing.source
                    ),
                ),
            )

            return True

        except Exception as e:

            print(f"Percepção da conversa falhou p/ '{profile}': {e}")

            return False

    @staticmethod
    def pending_line(profile: str) -> str:
        """Pro contexto do chat: há pergunta de esforço em aberto? Aí uma
        resposta em palavras ("foi tranquilo", "morri") é a resposta a ela."""

        try:

            pending = SessionRpeRepository().get_pending(profile)

        except Exception:

            return ""

        if not pending or not pending.get("day"):

            return ""

        try:

            day = date.fromisoformat(pending["day"])

        except ValueError:

            return ""

        return (
            f"PERGUNTA EM ABERTO: você perguntou como foi o esforço do treino "
            f"de {day.strftime('%d/%m')} — se a mensagem dele responde (mesmo "
            "em palavras), registre em \"perception\" com esse dia."
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _watch_feel(value) -> str | None:

        if value is None:

            return None

        try:

            key = min(WATCH_FEEL_WORDS, key=lambda k: abs(k - float(value)))

        except (TypeError, ValueError):

            return None

        return WATCH_FEEL_WORDS[key]

    @staticmethod
    def _run_on(profile: str, day: date):
        """A corrida (mais longa) daquele dia no arquivo permanente."""

        from app.application.history.weekly_buckets import activity_date
        from app.domain.value_objects.sports import is_foot_sport
        from app.infrastructure.persistence.activity_archive_repository import (
            ActivityArchiveRepository,
        )

        runs = [
            a for a in ActivityArchiveRepository().load_activities(profile)
            if is_foot_sport(a.sport) and activity_date(a) == day
        ]

        if not runs:

            return None

        return max(runs, key=lambda a: a.distance or 0)
