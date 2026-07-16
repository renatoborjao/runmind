import hashlib
import hmac

from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import Header
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings

from app.application.events.coach_conversation import (
    CoachConversationEvent,
)
from app.application.events.external_plan_received import (
    ExternalPlanEvent,
)
from app.application.events.onboarding_conversation import (
    OnboardingEvent,
)
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.events.training_completed import (
    TrainingCompletedEvent,
)
from app.application.use_cases.owner_resolver import (
    OwnerResolver,
)
from app.domain.value_objects.sports import (
    is_foot_sport,
)
from app.infrastructure.integrations.evolution.inbound_parser import (
    WhatsAppInboundParser,
)
from app.infrastructure.integrations.evolution.phone_normalizer import (
    PhoneNormalizer,
)
from app.application.garmin.garmin_activity_poller import (
    GarminActivityPoller,
)
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)
from app.infrastructure.integrations.strava.client import (
    StravaClient,
)
from app.infrastructure.integrations.telegram.telegram_inbound_parser import (
    TelegramInboundParser,
)
from app.infrastructure.integrations.whatsapp_cloud.whatsapp_cloud_inbound_parser import (
    WhatsAppCloudInboundParser,
)
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.processed_activity_guard import (
    ProcessedActivityGuard,
)
from app.infrastructure.persistence.processed_inbound_guard import (
    ProcessedInboundGuard,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


# ==========================================================
# STRAVA VERIFICATION
# ==========================================================

@router.get("/strava")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):

    if hub_mode != "subscribe":

        raise HTTPException(
            status_code=400,
            detail="Invalid hub.mode",
        )

    if hub_verify_token != "runmind123":

        raise HTTPException(
            status_code=403,
            detail="Invalid verify token",
        )

    return {

        "hub.challenge": hub_challenge

    }


# ==========================================================
# STRAVA EVENTS
# ==========================================================

@router.post("/strava")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):

    payload = await request.json()

    print()
    print("=" * 70)
    print("WEBHOOK RECEBIDO")
    print("=" * 70)
    print(payload)
    print("=" * 70)

    # Ignora eventos que não são de atividade
    if payload.get("object_type") != "activity":

        return {"ignored": True, "reason": "object_type != activity"}

    # Atividade apagada no Strava sai também do arquivo permanente —
    # senão treinos descartados (duplicados, registros errados) inflam
    # km de vida e histórico do atleta pra sempre. Tudo local e barato,
    # cabe dentro do prazo de ~2s do ack.
    if payload.get("aspect_type") == "delete":

        return _handle_activity_deleted(
            payload["owner_id"],
            payload["object_id"],
            background_tasks,
        )

    # Só treino recém-criado gera feedback. update não —
    # o que havia pra avaliar já foi avaliado na criação.
    if payload.get("aspect_type") != "create":

        return {
            "ignored": True,
            "reason": f"aspect_type {payload.get('aspect_type')}",
        }

    owner_id = payload["owner_id"]

    activity_id = payload["object_id"]

    # Idempotência: mesmo com ack rápido, o Strava pode reentregar o
    # mesmo evento. check_and_mark é síncrono e barato — descarta a
    # duplicata antes de agendar qualquer trabalho.
    if not ProcessedActivityGuard().check_and_mark(activity_id):

        return {"ignored": True, "reason": "duplicate activity"}

    # ACK RÁPIDO: o Strava exige resposta em ~2s, senão considera falha e
    # REENTREGA o evento (era a causa-raiz da mensagem duplicada). Buscar
    # atividade + streams + IA + envio passa disso, então respondemos 200
    # já e processamos em background.
    background_tasks.add_task(
        _process_strava_activity,
        owner_id,
        activity_id,
    )

    return {"queued": True, "activity_id": activity_id}


def _handle_activity_deleted(
    owner_id: int,
    activity_id: int,
    background_tasks: BackgroundTasks,
) -> dict:
    """Reflete no RunMind uma atividade apagada no Strava: tira do
    arquivo permanente, solta a marca de idempotência e — se o atleta
    já recebeu feedback desse treino — manda uma retratação pra ele
    saber que pode ignorar a análise (caso clássico: teste na esteira
    apagado logo em seguida). Falha aqui nunca vira 500 — o Strava
    reentregaria um evento que não temos como (nem por que)
    reprocessar."""

    try:

        profile = OwnerResolver.resolve(owner_id)

        guard = ProcessedActivityGuard()

        # marca no guard = passou pelo webhook; registro no arquivo =
        # gerou análise de corrida. Só as duas juntas provam que o
        # atleta recebeu feedback — evita retratação falsa quando ele
        # apaga uma pedalada ou um treino antigo de antes do RunMind.
        feedback_was_sent = guard.is_marked(activity_id)

        removed = ActivityArchiveRepository().remove(
            profile,
            activity_id,
        )

        # sem a atividade, a marca de "já processada" é órfã
        guard.unmark(activity_id)

        if feedback_was_sent and removed:

            # envio fora do caminho do ack (Telegram pode demorar)
            background_tasks.add_task(
                _send_deletion_retraction,
                profile,
                activity_id,
            )

        print(
            f"Atividade {activity_id} apagada no Strava "
            f"({profile}): removida do arquivo = {removed}, "
            f"retratação = {feedback_was_sent and removed}"
        )

        return {
            "deleted": True,
            "removed_from_archive": removed,
            "retraction_queued": feedback_was_sent and removed,
        }

    except Exception as e:

        # dono desconhecido (atleta não cadastrado) ou falha de disco:
        # loga e responde 200 mesmo assim
        print(
            f"Falha ao tratar delete da atividade {activity_id} "
            f"(owner {owner_id}): {e}"
        )

        return {"ignored": True, "reason": "delete não aplicável"}


async def _send_deletion_retraction(
    profile: str,
    activity_id: int,
) -> None:
    """Avisa o atleta que a análise enviada não vale mais. Sem isso a
    mensagem de parabéns por um teste/registro errado ficaria no chat
    como se fosse treino de verdade."""

    try:

        runner = RunnerProfileRepository().load(profile)

        await NotificationService.send(
            runner,
            (
                "🏃 RunMind\n\n"
                "Vi que você apagou aquele treino no Strava. 👍\n\n"
                "Pode desconsiderar a análise que te mandei — "
                "ele também já saiu do seu histórico por aqui."
            ),
        )

    except Exception as e:

        print(
            f"Falha ao enviar retratação da atividade {activity_id} "
            f"({profile}): {e}"
        )


async def _process_strava_activity(
    owner_id: int,
    activity_id: int,
) -> None:
    """Trabalho pesado do webhook, fora do caminho da resposta. Falha aqui
    nunca derruba nada (o 200 já foi dado); só loga e solta a marca pra uma
    eventual reentrega poder reprocessar."""

    try:

        profile = OwnerResolver.resolve(owner_id)

        # atleta com Garmin conectado é analisado pelos DADOS do Garmin
        # (voltas rotuladas, tiros exatos). Como o Garmin é upstream do
        # Strava (relógio→Garmin→Strava), quando este webhook chega a
        # atividade já está no Garmin — então usamos o webhook como GATILHO
        # instantâneo pra analisar via Garmin (dedup evita repetir com o
        # poller de 10 min). Não consumimos o dado do Strava.
        if (
            GarminClient.is_connected(profile)
            and GarminClient.analysis_enabled(profile)
        ):

            print(f"Garmin ligado: analisando '{profile}' via Garmin")

            await GarminActivityPoller.poll_one(profile)

            return

        client = StravaClient(profile)

        activity = await client.get_activity(activity_id)

        # stream segundo-a-segundo (velocidade/FC): revela tiros curtos
        # que os splits por km borram. Indisponível NUNCA derruba o fluxo.
        try:

            activity.raw["_streams"] = await client.get_activity_streams(
                activity_id,
            )

        except Exception as stream_error:

            print(f"Streams indisponíveis p/ {activity_id}: {stream_error}")

        # pedalada/natação/musculação não geram feedback de corrida
        if not is_foot_sport(activity.sport):

            print(f"Ignorado: sport não suportado ({activity.sport})")

            return

        # corrida sem distância (esteira/HIIT sem sensor): não dá pra analisar
        # pace — pula sem crashar (o enricher dividiria por zero)
        if not activity.distance:

            print(f"Ignorado: atividade sem distância ({activity_id})")

            return

        await TrainingCompletedEvent.execute(
            profile=profile,
            activity=activity,
        )

    except Exception as e:

        # solta a marca pra uma reentrega legítima do Strava poder tentar
        # de novo (senão o treino ficaria sem feedback pra sempre)
        ProcessedActivityGuard().unmark(activity_id)

        print(
            f"Falha ao processar atividade {activity_id} "
            f"(owner {owner_id}): {e}"
        )


# ==========================================================
# TEST
# ==========================================================

@router.post("/strava/test/{profile}")
async def test_pipeline(
    profile: str,
):

    try:

        result = await TrainingCompletedEvent.execute(
            profile=profile,
        )

        return {

            "status": "success",

            "runner": result["runner"].name,

            "message": result["message"],

        }

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e),

        )


# ==========================================================
# WHATSAPP INBOUND (Evolution API)
# ==========================================================

@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):

    payload = await request.json()

    print()
    print("=" * 70)
    print("WHATSAPP WEBHOOK RECEBIDO")
    print("=" * 70)
    print(payload)
    print("=" * 70)

    if payload.get("event") != "messages.upsert":

        return {

            "ignored": True,

            "reason": "event != messages.upsert",

        }

    data = payload.get("data", {})

    if data.get("key", {}).get("fromMe"):

        return {

            "ignored": True,

            "reason": "fromMe == true",

        }

    raw_phone = data.get("key", {}).get("remoteJid", "")

    if WhatsAppInboundParser.is_group_message(raw_phone):

        return {

            "ignored": True,

            "reason": "group or broadcast message",

        }

    text = WhatsAppInboundParser.extract_text(data)

    media = WhatsAppInboundParser.extract_media(data)

    if not text and not media:

        return {

            "ignored": True,

            "reason": "no supported content found",

        }

    phone = PhoneNormalizer.normalize(raw_phone)

    # Idempotência + ack rápido: a Evolution reenvia o webhook em erro (ou
    # quando o ack demora), reprocessando a mesma mensagem — tempestade de
    # retry + chamadas duplicadas ao Gemini. Descarta a reentrega e tira o
    # trabalho pesado do caminho da resposta.
    message_id = (data.get("key") or {}).get("id")

    if (
        message_id
        and not ProcessedInboundGuard().check_and_mark(f"wa:{message_id}")
    ):

        return {"ignored": True, "reason": "duplicate message"}

    background_tasks.add_task(
        _run_inbound,
        channel="whatsapp",
        address=phone,
        text=text,
        media=media,
        sender_name=data.get("pushName", ""),
    )

    return {"queued": True, "message_id": message_id}


async def route_inbound(
    channel: str,
    address: str,
    text: str | None,
    media: dict | None,
    sender_name: str,
) -> dict:
    """Roteamento agnóstico ao canal (WhatsApp/Telegram): resolve o
    atleta pelo endereço e despacha onboarding, plano externo ou
    conversa."""

    repo = RunnerProfileRepository()

    if channel == "telegram":

        profile = repo.find_by_telegram_id(address)

    else:

        profile = repo.find_by_phone(address)

    # endereço desconhecido: inicia (ou continua) o cadastro
    if profile is None:

        reply = await OnboardingEvent.execute(
            channel=channel,
            address=address,
            incoming_text=text or "",
            sender_name=sender_name,
            media=media,
        )

        return {

            "success": True,

            "onboarding": True,

            "reply_sent": bool(reply),

        }

    # mídia de atleta cadastrado: plano do treinador (se aplicável)
    if media is not None:

        reply = await _handle_profile_media(profile, media)

        return {

            "success": True,

            "profile": profile,

            "reply_sent": bool(reply),

        }

    reply = await CoachConversationEvent.execute(
        profile=profile,
        incoming_text=text,
        sender_name=sender_name,
    )

    return {

        "success": True,

        "profile": profile,

        "reply_sent": bool(reply),

    }


async def _run_inbound(
    channel: str,
    address: str,
    text: str | None,
    media: dict | None,
    sender_name: str,
) -> None:
    """Processa a mensagem FORA do caminho do ack. O webhook já respondeu
    200 (o canal não vai reentregar), então uma falha aqui nunca pode
    derrubar nada nem virar retry: o próprio fluxo do coach já manda um
    fallback ao atleta em caso de indisponibilidade. Só logamos."""

    try:

        await route_inbound(
            channel=channel,
            address=address,
            text=text,
            media=media,
            sender_name=sender_name,
        )

    except Exception as e:

        print(
            f"Falha ao processar mensagem de {channel} {address}: {e}"
        )


async def _handle_profile_media(
    profile: str,
    media: dict,
) -> str:

    runner = RunnerProfileRepository().load(profile)

    if runner.external_coach:

        return await ExternalPlanEvent.execute(
            profile=profile,
            media=media,
        )

    reply = (
        "Recebi sua imagem! 📷 Por enquanto eu só leio planos de "
        "treinador de quem treina com um — e o seu plano é comigo "
        "mesmo. 😉 Se você passou a treinar com um treinador, me "
        "avisa que eu registro."
    )

    await NotificationService.send(
        runner,
        reply,
    )

    return reply


# ==========================================================
# TELEGRAM INBOUND
# ==========================================================

@router.post("/telegram")
async def receive_telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):

    settings = get_settings()

    secret = settings.telegram_webhook_secret

    if secret and x_telegram_bot_api_secret_token != secret:

        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram secret token",
        )

    update = await request.json()

    print()
    print("=" * 70)
    print("TELEGRAM WEBHOOK RECEBIDO")
    print("=" * 70)
    print(update)
    print("=" * 70)

    message = TelegramInboundParser.message(update)

    if message is None or TelegramInboundParser.is_from_bot(message):

        return {"ignored": True, "reason": "no direct message"}

    chat_id = TelegramInboundParser.chat_id(message)

    if chat_id is None:

        return {"ignored": True, "reason": "no chat id"}

    text = TelegramInboundParser.extract_text(message)

    media = TelegramInboundParser.extract_media(message)

    if not text and not media:

        return {"ignored": True, "reason": "no supported content found"}

    # Idempotência: o Telegram reentrega o MESMO update quando o ack
    # demora. check_and_mark é síncrono e barato — descarta a reentrega
    # antes de agendar qualquer trabalho, pra a mesma mensagem nunca
    # gerar duas respostas (a enxurrada de "me embananei").
    update_id = TelegramInboundParser.update_id(update)

    if (
        update_id is not None
        and not ProcessedInboundGuard().check_and_mark(f"tg:{update_id}")
    ):

        return {"ignored": True, "reason": "duplicate update"}

    # ACK RÁPIDO: responde 200 já e processa em background. Buscar
    # contexto + IA (com retry/backoff) + envio passa do prazo do
    # Telegram, que senão considera falha e REENTREGA o update — era o
    # que multiplicava a resposta. Tirar isso do caminho do ack corta a
    # reentrega na raiz; a idempotência acima cobre o resto.
    background_tasks.add_task(
        _run_inbound,
        channel="telegram",
        address=chat_id,
        text=text,
        media=media,
        sender_name=TelegramInboundParser.sender_name(message),
    )

    return {"queued": True, "update_id": update_id}


# ==========================================================
# WHATSAPP INBOUND (Cloud API oficial da Meta)
# ==========================================================

@router.get("/whatsapp-cloud")
async def verify_whatsapp_cloud_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """Handshake da Meta: ela chama este GET uma vez ao configurar o
    webhook e espera o hub.challenge de volta, em texto puro, se o token
    conferir com o nosso."""

    settings = get_settings()

    if (
        hub_mode == "subscribe"
        and hub_verify_token == settings.whatsapp_verify_token
        and settings.whatsapp_verify_token
    ):

        return PlainTextResponse(hub_challenge)

    raise HTTPException(status_code=403, detail="Invalid verify token")


def _valid_cloud_signature(
    body: bytes,
    signature_header: str,
) -> bool:
    """Confere o X-Hub-Signature-256 (HMAC-SHA256 do corpo cru com o app
    secret). Sem app secret configurado, não bloqueia — deixa passar pra
    não travar teste local; em produção configure WHATSAPP_APP_SECRET."""

    settings = get_settings()

    if not settings.whatsapp_app_secret:

        return True

    if not signature_header.startswith("sha256="):

        return False

    expected = hmac.new(
        settings.whatsapp_app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header.split("sha256=", 1)[1]

    return hmac.compare_digest(expected, received)


@router.post("/whatsapp-cloud")
async def receive_whatsapp_cloud_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
):

    raw_body = await request.body()

    if not _valid_cloud_signature(raw_body, x_hub_signature_256):

        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()

    print()
    print("=" * 70)
    print("WHATSAPP CLOUD WEBHOOK RECEBIDO")
    print("=" * 70)
    print(payload)
    print("=" * 70)

    parsed = WhatsAppCloudInboundParser.first_message(payload)

    # status (entregue/lido), reações, etc. não têm mensagem de usuário
    if parsed is None:

        return {"ignored": True, "reason": "no user message"}

    message = parsed["message"]

    value = parsed["value"]

    text = WhatsAppCloudInboundParser.extract_text(message)

    media = WhatsAppCloudInboundParser.extract_media(message)

    if not text and not media:

        return {"ignored": True, "reason": "no supported content found"}

    raw_phone = WhatsAppCloudInboundParser.sender_phone(message)

    if not raw_phone:

        return {"ignored": True, "reason": "no sender phone"}

    phone = PhoneNormalizer.normalize(raw_phone)

    # Idempotência + ack rápido: a Meta reentrega o webhook em erro (ou
    # quando o ack demora), reprocessando a mesma mensagem — retry +
    # chamadas duplicadas ao Gemini. Descarta a reentrega pelo wamid e
    # tira o trabalho pesado do caminho da resposta (sempre 200 rápido).
    message_id = message.get("id")

    if (
        message_id
        and not ProcessedInboundGuard().check_and_mark(f"wac:{message_id}")
    ):

        return {"ignored": True, "reason": "duplicate message"}

    background_tasks.add_task(
        _run_inbound,
        channel="whatsapp",
        address=phone,
        text=text,
        media=media,
        sender_name=WhatsAppCloudInboundParser.sender_name(value),
    )

    return {"queued": True, "message_id": message_id}