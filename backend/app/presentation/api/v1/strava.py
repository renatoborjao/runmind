from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
import httpx

from app.application.planner.strava_connect_refresh import (
    StravaConnectRefresh,
)
from app.application.services.strava.webhook_service import (
    WebhookService,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.config import get_settings
from app.infrastructure.integrations.evolution.phone_normalizer import (
    PhoneNormalizer,
)
from app.infrastructure.integrations.strava.client import (
    StravaClient,
)
from app.infrastructure.persistence.onboarding_state_repository import (
    OnboardingStateRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.storage.token_store import (
    TokenStore,
)

router = APIRouter(
    prefix="/strava",
    tags=["Strava"],
)


# ==========================================================
# OAUTH
# ==========================================================

@router.get("/connect")
async def connect(state: str = ""):
    """`state` carrega o telefone normalizado do corredor — é assim que
    o callback sabe de quem são os tokens (multiatleta/onboarding)."""

    settings = get_settings()

    redirect_uri = (
        f"{settings.public_base_url}/api/v1/strava/callback"
    )

    url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={settings.strava_client_id}"
        "&response_type=code"
        f"&redirect_uri={redirect_uri}"
        "&approval_prompt=force"
        "&scope=read,activity:read_all"
    )

    if state:

        url += f"&state={state}"

    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    background_tasks: BackgroundTasks,
    code: str,
    state: str = "",
):

    settings = get_settings()

    async with httpx.AsyncClient() as client:

        response = await client.post(

            "https://www.strava.com/oauth/token",

            data={

                "client_id": settings.strava_client_id,

                "client_secret": settings.strava_client_secret,

                "code": code,

                "grant_type": "authorization_code",

            },

        )

    if response.status_code != 200:

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    data = response.json()

    athlete_id = (data.get("athlete") or {}).get("id")

    profile, source = _resolve_token_target(state)

    TokenStore(profile).save(
        {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": data["expires_at"],
        }
    )

    if athlete_id:

        _persist_athlete_id(
            source,
            profile,
            state,
            athlete_id,
        )

    # Perfil já cadastrado (LATE CONNECTOR): conectou o Strava depois do
    # cadastro, quando o plano já saiu conservador (histórico vazio). Agora
    # que o histórico chegou, regenera o plano da semana com o retrato real
    # e manda pro atleta — em BACKGROUND, porque gerar o plano pela IA passa
    # do tempo do redirect do OAuth. O refresh já carrega e arquiva o
    # histórico (e cobre treinador externo / reconexão internamente).
    #
    # Onboarding em andamento: aqui só arquiva o histórico (o plano é montado
    # na conclusão do cadastro, que já usa o Strava recém-conectado). Falha
    # não derruba a conexão (o histórico também carrega depois).
    if source == "profile":

        background_tasks.add_task(
            StravaConnectRefresh.refresh,
            profile,
        )

    else:

        try:

            await LoadTrainingHistory.execute(profile=profile)

        except Exception as e:

            print(
                f"Falha ao pré-carregar histórico de '{profile}' "
                f"na conexão do Strava: {e}"
            )

    return {

        "message": "Strava conectado com sucesso.",

        "profile": profile,

        "saved": True,

    }


def _parse_state(state: str) -> tuple[str, str]:
    """`state` do OAuth -> (channel, address_key).

    - "tg:<chat_id>"  -> ("telegram", chat_id)
    - "wa:<telefone>" -> ("whatsapp", telefone normalizado)
    - sem prefixo     -> ("whatsapp", telefone normalizado) [retrocompat]
    """

    if state.startswith("tg:"):

        return "telegram", state[3:]

    raw = state[3:] if state.startswith("wa:") else state

    return "whatsapp", PhoneNormalizer.normalize(raw)


def _resolve_token_target(state: str) -> tuple[str, str]:
    """De quem são os tokens: (profile/slug, origem).

    - sem state: comportamento original (renato);
    - perfil existente (por telefone ou telegram_id): o próprio perfil;
    - onboarding em andamento: o slug reservado.
    """

    if not state:

        return "renato", "profile"

    channel, address = _parse_state(state)

    repo = RunnerProfileRepository()

    if channel == "telegram":

        profile = repo.find_by_telegram_id(address)

    else:

        profile = repo.find_by_phone(address)

    if profile is not None:

        return profile, "profile"

    onboarding = OnboardingStateRepository().load(address)

    if onboarding and onboarding.get("slug"):

        return onboarding["slug"], "onboarding"

    raise HTTPException(
        status_code=400,
        detail=(
            "Nenhum cadastro encontrado para este link. "
            "Comece a conversa com o coach primeiro."
        ),
    )


def _persist_athlete_id(
    source: str,
    profile: str,
    state: str,
    athlete_id: int,
) -> None:

    if source == "profile":

        RunnerProfileRepository().update_fields(
            profile,
            {"strava_athlete_id": athlete_id},
        )

        return

    # onboarding em andamento: o id vai pro perfil na conclusão
    _, address = _parse_state(state)

    repo = OnboardingStateRepository()

    onboarding = repo.load(address) or {}

    onboarding["strava_athlete_id"] = athlete_id

    repo.save(address, onboarding)


# ==========================================================
# ATHLETE
# ==========================================================

@router.get("/me")
async def me():

    client = StravaClient()

    access_token = await client._get_access_token()

    async with httpx.AsyncClient(
        timeout=10,
    ) as http:

        response = await http.get(

            "https://www.strava.com/api/v3/athlete",

            headers={

                "Authorization": f"Bearer {access_token}"

            },

        )

    response.raise_for_status()

    athlete = response.json()

    return {

        "id": athlete["id"],

        "username": athlete.get("username"),

        "firstname": athlete.get("firstname"),

        "lastname": athlete.get("lastname"),

        "city": athlete.get("city"),

        "country": athlete.get("country"),

    }


# ==========================================================
# WEBHOOKS
# ==========================================================

@router.post("/register-webhook")
async def register_webhook():

    callback_url = (
        "https://unopened-employed-cedar.ngrok-free.dev"
        "/api/v1/webhooks/strava"
    )

    return await WebhookService.register(
        callback_url,
    )


@router.get("/subscriptions")
async def subscriptions():

    return await WebhookService.subscriptions()


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: int,
):

    return await WebhookService.delete(
        subscription_id,
    )