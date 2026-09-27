from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import RedirectResponse
import httpx

from app.application.coach.intelligence.personal_record_detector import (
    PersonalRecordDetector,
)
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
from app.infrastructure.security.session_token import SessionToken
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

# Link do Strava pro atleta do APP: a identidade vai no `state` como token
# assinado de uso restrito (não é a sessão), vence rápido e só serve pra isso.
APP_STATE_PREFIX = "app:"

APP_STATE_PURPOSE = "strava_connect"

_APP_STATE_TTL_SECONDS = 30 * 60

# pra onde o atleta volta no app depois do Strava (lista fechada: nada de
# redirect aberto vindo de parâmetro)
_APP_BACK = {"perfil": "/perfil", "onboarding": "/onboarding"}


def _authorize_url(state: str) -> str:

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
        # activity:write habilita renomear o treino no Strava com o nome do
        # nosso plano ("Tempo 6 km"). Só é USADO nos perfis do canário
        # (strava_rename_active_for); pra os demais é permissão inócua.
        "&scope=read,activity:read_all,activity:write"
    )

    if state:

        url += f"&state={state}"

    return url


def _app_state(back: str, token: str) -> str:
    """`app:<volta>:<token>` — o token (base64url + ponto) nunca tem ':'."""

    return f"{APP_STATE_PREFIX}{back}:{token}"


def _split_app_state(state: str) -> tuple[str, str]:
    """`app:<volta>:<token>` -> (volta, token). Volta desconhecida = perfil."""

    rest = state[len(APP_STATE_PREFIX):]

    back, _, token = rest.partition(":")

    if back not in _APP_BACK:

        return "perfil", rest

    return back, token


def _app_redirect(state: str, status: str) -> RedirectResponse:
    """Volta pra tela do app de onde o atleta saiu (`?strava=ok|erro`)."""

    back, _ = _split_app_state(state)

    base = get_settings().app_base_url.rstrip("/")

    return RedirectResponse(f"{base}{_APP_BACK[back]}?strava={status}")


@router.get("/connect")
async def connect(state: str = ""):
    """`state` carrega o telefone normalizado do corredor — é assim que
    o callback sabe de quem são os tokens (multiatleta/onboarding)."""

    return RedirectResponse(_authorize_url(state))


@router.get("/app-connect")
async def app_connect(request: Request, back: str = "perfil"):
    """Botão "Conectar Strava" do app (Perfil ou passo do cadastro): o navegador
    vem pra cá com o cookie de sessão; a gente troca a sessão por um `state` de
    uso restrito e manda pro Strava. Sem sessão, volta pro login do app."""

    profile = SessionToken.verify(
        request.cookies.get(get_settings().auth_cookie_name)
    )

    if not profile:

        base = get_settings().app_base_url.rstrip("/")

        return RedirectResponse(f"{base}/entrar")

    token = SessionToken.issue(
        profile,
        purpose=APP_STATE_PURPOSE,
        ttl_seconds=_APP_STATE_TTL_SECONDS,
    )

    back = back if back in _APP_BACK else "perfil"

    return RedirectResponse(_authorize_url(_app_state(back, token)))


@router.get("/callback")
async def callback(
    background_tasks: BackgroundTasks,
    code: str = "",
    state: str = "",
    scope: str = "",
    error: str = "",
):

    # Veio do app: o atleta volta pra tela de onde saiu (Perfil ou cadastro)
    # com o resultado — nunca cai num JSON cru nem numa tela de erro.
    if state.startswith(APP_STATE_PREFIX):

        if error or not code:

            return _app_redirect(state, "erro")

        try:

            await _complete_connection(
                background_tasks, code, state, scope,
            )

        except Exception as e:

            print(f"Falha ao conectar Strava pelo app: {getattr(e, 'detail', e)}")

            return _app_redirect(state, "erro")

        return _app_redirect(state, "ok")

    if error or not code:

        raise HTTPException(
            status_code=400,
            detail="Conexão com o Strava não autorizada.",
        )

    profile = await _complete_connection(
        background_tasks, code, state, scope,
    )

    return {

        "message": "Strava conectado com sucesso.",

        "profile": profile,

        "saved": True,

    }


async def _complete_connection(
    background_tasks: BackgroundTasks,
    code: str,
    state: str,
    scope: str,
) -> str:
    """Troca o `code` pelos tokens, grava no perfil certo e dispara o que vem
    depois da conexão (refresh do plano / pré-carga do histórico). Devolve o
    perfil. Levanta HTTPException se a troca falhar ou o `state` não resolver."""

    settings = get_settings()

    # resolve ANTES de trocar o code: state inválido não gasta a autorização
    profile, source = _resolve_token_target(state)

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

    TokenStore(profile).save(
        {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": data["expires_at"],
            # o Strava manda no redirect o que o atleta REALMENTE concedeu
            # (ele pode desmarcar activity:write na tela). Guardar aqui deixa
            # o rename saber ANTES de tentar quem tem escrita — sem depender do
            # 401. Refresh preserva este valor (não vem no refresh). Ver
            # StravaClient.can_write e /debug/strava-rename.
            "scope": scope,
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

        # Semeia os recordes já aqui (mesmo ainda em onboarding): o slug é
        # estável e vira o profile.id final, então o primeiro treino de
        # verdade do atleta já vai comparar contra a base certa.
        try:

            await PersonalRecordDetector.seed(profile)

        except Exception as e:

            print(
                f"Falha ao semear recordes de '{profile}' "
                f"na conexão do Strava: {e}"
            )

    return profile


def _parse_state(state: str) -> tuple[str, str]:
    """`state` do OAuth -> (channel, address_key).

    - "app:<volta>:<token>" -> ("app", token assinado de uso restrito)
    - "tg:<chat_id>"  -> ("telegram", chat_id)
    - "wa:<telefone>" -> ("whatsapp", telefone normalizado)
    - sem prefixo     -> ("whatsapp", telefone normalizado) [retrocompat]
    """

    if state.startswith(APP_STATE_PREFIX):

        return "app", _split_app_state(state)[1]

    if state.startswith("tg:"):

        return "telegram", state[3:]

    raw = state[3:] if state.startswith("wa:") else state

    return "whatsapp", PhoneNormalizer.normalize(raw)


def _resolve_token_target(state: str) -> tuple[str, str]:
    """De quem são os tokens: (profile/slug, origem).

    - perfil existente (por telefone ou telegram_id): o próprio perfil;
    - onboarding em andamento: o slug reservado.

    Sem state não dá pra saber de quem é o callback — antes isso caía num
    perfil fixo ("renato"), o que num app multi-atleta gravaria tokens no
    dono errado. Agora rejeita, igual a um cadastro não encontrado.
    """

    if not state:

        raise HTTPException(
            status_code=400,
            detail=(
                "Link do Strava sem identificação. "
                "Comece a conversa com o coach primeiro."
            ),
        )

    channel, address = _parse_state(state)

    repo = RunnerProfileRepository()

    if channel == "app":

        # token do app: assinado, com finalidade e prazo; o perfil tem que
        # existir (o atleta do app sempre já tem perfil — nasce no cadastro)
        slug = SessionToken.verify(address, purpose=APP_STATE_PURPOSE)

        if slug and repo.exists(slug):

            # conectou no MEIO do cadastro (perfil-esqueleto): igual ao bot, só
            # arquiva o histórico — o plano sai na conclusão, já com ele
            if not repo.load(slug).onboarding_complete:

                return slug, "app_onboarding"

            return slug, "profile"

        raise HTTPException(
            status_code=400,
            detail="Link do Strava vencido ou inválido. Tente de novo pelo app.",
        )

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

    # atleta do app sempre tem perfil (mesmo em cadastro): o id vai direto nele
    if source in ("profile", "app_onboarding"):

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

    # domínio público atual (settings), nunca fixo: a URL cravada no ngrok
    # velho deixou o webhook do Strava mudo desde a migração pra Oracle.
    callback_url = (
        f"{get_settings().public_base_url.rstrip('/')}"
        "/api/v1/webhooks/strava"
    )

    # reaponta: apaga inscrição velha (outro domínio) e cria a nova numa
    # chamada só — o Strava recusa registrar com uma antiga no lugar
    return await WebhookService.repoint(
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