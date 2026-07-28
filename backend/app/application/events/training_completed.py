from app.application.coach.conversation.rpe_flow import RpeFlow
from app.application.coach.intelligence.personal_record_detector import (
    PersonalRecordDetector,
)
from app.application.coach.intelligence.proactive_aversion_detector import (
    ProactiveAversionDetector,
)
from app.application.coach.intelligence.race_debrief import RaceDebrief
from app.application.notifications.coach_outbox import (
    CoachOutbox,
)
from app.application.orchestrators.training_pipeline import (
    TrainingPipeline,
)
from app.domain.entities.activity import (
    Activity,
)
from app.infrastructure.persistence.session_rpe_repository import (
    SessionRpeRepository,
)


class TrainingCompletedEvent:

    @staticmethod
    async def execute(
        profile: str,
        activity: Activity | None = None,
    ):

        result = await TrainingPipeline.execute(
            profile=profile,
            activity=activity,
        )

        runner = result["runner"]

        message = result["message"]

        # sRPE: pergunta o esforço percebido junto do feedback e marca o treino
        # como pendente de RPE (o número que o atleta responder vira carga
        # subjetiva). Best-effort — nunca derruba o feedback.
        try:

            message = TrainingCompletedEvent._ask_rpe(profile, result, message)

        except Exception as e:

            print(f"Falha ao preparar RPE de '{profile}': {e}")

        # CoachOutbox: envia E registra no outbox (pra o coach lembrar da
        # análise quando o atleta comentar depois no chat)
        await CoachOutbox.send(
            runner,
            message,
        )

        # Detector proativo de aversão (Fatia 2): depois do feedback, se está
        # virando PADRÃO evitar um estímulo de qualidade, ABRE uma conversa —
        # nunca muda o plano. Falha aqui jamais derruba o feedback já enviado.
        try:

            nudge = ProactiveAversionDetector.after_feedback(
                runner,
                result["planned_session"],
                result["activity"],
            )

            if nudge:

                await CoachOutbox.send(runner, nudge)

        except Exception as e:

            print(f"Falha no detector proativo de aversão: {e}")

        # Celebração de PR/marcos: reconhece recorde batido (corrida mais
        # longa, treino mais rápido na faixa, km acumulado, semana de maior
        # volume). Fonte = Strava (obrigatório no onboarding), nunca Garmin —
        # mantém o "livro de recordes" único mesmo pra quem é analisado via
        # Garmin. Vale pra TODOS os atletas, inclusive treinador externo —
        # não mexe no plano, só comemora. Falha aqui jamais derruba o
        # feedback já enviado.
        try:

            celebration = await PersonalRecordDetector.after_feedback(
                runner,
            )

            if celebration:

                # recorde batido é beat emocional: sai em texto + áudio
                await CoachOutbox.send(
                    runner, celebration, voice=True, profile=profile,
                )

        except Exception as e:

            print(f"Falha na celebração de recorde: {e}")

        # Debrief de prova: se ESTE treino foi a prova-alvo (data + distância),
        # manda a análise especial do dia (resultado vs meta) e consome a data.
        # Vale pra todos, inclusive treinador externo — é reconhecimento, não
        # muda plano. Falha aqui jamais derruba o feedback já enviado.
        try:

            debrief = await RaceDebrief.after_feedback(
                profile,
                runner,
                result["activity"],
            )

            if debrief:

                # "você conseguiu / cruzou": beat emocional em texto + áudio
                await CoachOutbox.send(
                    runner, debrief, voice=True, profile=profile,
                )

        except Exception as e:

            print(f"Falha no debrief de prova: {e}")

        return result

    # treinos em que o esforço PERCEBIDO informa de verdade — a rodagem leve
    # tem RPE previsível (não vale perguntar). Casa por substring no rótulo,
    # cobrindo tanto o rótulo do plano em PT (Velocidade/Longão/Tempo/Limiar/
    # Tiros/Progressivo) quanto o tipo detectado em inglês (WorkoutType:
    # TEMPO/THRESHOLD/VO2/INTERVAL/LONG_RUN/RACE).
    _DEMANDING_CUES = (
        "veloc", "tiro", "interval", "limiar", "threshold", "ritmo", "tempo",
        "progress", "fartlek", "vo2", "forte", "long", "race", "prova",
    )

    @staticmethod
    def _ask_rpe(profile: str, result: dict, message: str) -> str:
        """Marca o treino como pendente de RPE e anexa a pergunta — SÓ em
        treino exigente (tiro/longão/tempo/...), com duração de verdade. Numa
        rodagem leve, o RPE é previsível e a pergunta vira ruído."""

        enriched = result.get("activity")

        activity = getattr(enriched, "activity", None)

        if activity is None or not activity.moving_time:

            return message

        if not TrainingCompletedEvent._is_demanding(result):

            return message

        SessionRpeRepository().set_pending(
            profile,
            activity_id=activity.id,
            day=activity.start_date.date().isoformat(),
            duration_min=round(activity.moving_time / 60, 1),
        )

        return f"{message}\n\n{RpeFlow.ASK_LINE}"

    @staticmethod
    def _is_demanding(result: dict) -> bool:
        """Treino de qualidade? Olha o rótulo planejado E o tipo detectado."""

        labels = []

        planned = result.get("planned_session")

        if planned is not None:

            labels.append(getattr(planned, "workout_type", "") or "")

        enriched = result.get("activity")

        if enriched is not None:

            labels.append(getattr(enriched, "training_type", "") or "")

        text = " ".join(labels).lower()

        return any(cue in text for cue in TrainingCompletedEvent._DEMANDING_CUES)