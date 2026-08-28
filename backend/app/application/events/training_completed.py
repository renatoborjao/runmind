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

        # Contador de km por TÊNIS: atribui esta corrida ao par certo (gear →
        # regra → padrão) e soma a km, sem o atleta tagar. Vale pra todos
        # (inclusive prova e treinador externo — o solado é dele). Roda ANTES do
        # feedback pra a nota "contei no X" ir na MESMA mensagem. Silencioso pra
        # quem não montou o armário. Nunca derruba o feedback.
        shoe_outcome = TrainingCompletedEvent._attribute_shoe(profile, runner, result)

        # Se ESTE treino é a prova-alvo, o dia é da PROVA: o feedback de treino
        # comum ("Parabéns pelo treino", "Tipo: Ritmo", "Intensidade: Leve",
        # RPE pra calibrar carga, "retomamos no próximo plano") NÃO sai — quem
        # conduz é o debrief de prova, o relatório do dia (mais abaixo). Era a
        # queixa do Renato: a prova tratada como "mais um treino".
        is_race = RaceDebrief.is_target_race(runner, result["activity"])

        if not is_race:

            message = result["message"]

            # sRPE: pergunta o esforço percebido junto do feedback e marca o
            # treino como pendente de RPE (o número vira carga subjetiva).
            # Best-effort — nunca derruba o feedback. (Numa PROVA não faz
            # sentido perguntar RPE "pra calibrar carga".)
            try:

                message = TrainingCompletedEvent._ask_rpe(profile, result, message)

            except Exception as e:

                print(f"Falha ao preparar RPE de '{profile}': {e}")

            # nota passiva do tênis: "contei essa no teu X — se foi outro, é só
            # falar". Afirmação (não pergunta), na MESMA mensagem — mantém a
            # conta certa sem exigir resposta; ele corrige se tiver trocado.
            message += TrainingCompletedEvent._shoe_note(shoe_outcome)

            # CoachOutbox: envia E registra no outbox (pra o coach lembrar da
            # análise quando o atleta comentar depois no chat). ESSENCIAL: ele
            # acabou de correr — sempre sai (isenta do teto do governador).
            await CoachOutbox.send(
                runner,
                message,
                profile=profile,
                kind="feedback",
            )

            # Detector proativo de aversão (Fatia 2): depois do feedback, se
            # está virando PADRÃO evitar um estímulo de qualidade, ABRE uma
            # conversa — nunca muda o plano. (Numa prova não se aplica.) Falha
            # aqui jamais derruba o feedback já enviado.
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
                    kind="personal_record",
                )

        except Exception as e:

            print(f"Falha na celebração de recorde: {e}")

        # Coaching de FORMA (cadência): agora é um LOOP guiado pela evolução no
        # resumo de domingo (CadenceProgressNotifier) — acompanha, reconhece
        # progresso e celebra o alvo, em vez de uma dica solta por corrida.

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
                    kind="race_debrief",
                )

        except Exception as e:

            print(f"Falha no debrief de prova: {e}")

        # Alerta de DESGASTE (par cruzou a vida útil): mensagem própria, é um
        # chamado à ação. Um por par (dedup no serviço). Vale pra todos.
        if shoe_outcome and shoe_outcome.wear_alert:

            await CoachOutbox.send(
                runner, shoe_outcome.wear_alert, profile=profile,
                kind="shoe_wear",
            )

        return result

    @staticmethod
    def _attribute_shoe(profile: str, runner, result):
        """Atribui a corrida ao tênis e soma a km. None se não há armário/não
        deu. Best-effort — nunca derruba o feedback."""

        try:

            from app.application.shoes.shoe_mileage_service import (
                ShoeMileageService,
            )

            return ShoeMileageService.attribute(
                profile,
                runner.name,
                result["activity"],
                result.get("planned_session"),
            )

        except Exception as e:

            print(f"Falha no contador de tênis de '{profile}': {e}")

            return None

    @staticmethod
    def _shoe_note(shoe_outcome) -> str:
        """Nota passiva pra emendar no feedback: qual par recebeu a km, com o
        convite a corrigir. Vazia quando não houve atribuição (sem armário)."""

        if shoe_outcome is None:

            return ""

        return (
            f"\n\n👟 Contei essa no teu {shoe_outcome.shoe.label} — se foi "
            "outro, é só me falar que eu ajusto."
        )

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