"""Foto/áudio pro coach (app e Telegram): a mídia vira texto que o coach lê e
segue pelo MESMO pipeline da conversa; planilha de treinador externo vira plano;
falha nunca vira silêncio."""

import asyncio
import base64
import io
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from app.application.coach.media.coach_media_message import (
    UNOPENABLE_IMAGE_REPLY,
    UNSEEN_IMAGE_REPLY,
    VOICE_TOO_LONG_REPLY,
    VOICE_UNHEARD_REPLY,
    CoachMediaMessage,
    compose_image_text,
)
from app.infrastructure.persistence.chat_media_store import ChatMediaStore
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.security.session_token import SessionToken
from app.main import app
from tests.coach.factories import make_runner

MOD = "app.application.coach.media.coach_media_message"

API = "app.presentation.api.v1.coach"

MEDIA_ID = "a" * 32


def _jpeg(size=(40, 30)) -> bytes:

    out = io.BytesIO()

    Image.new("RGB", size, (200, 80, 20)).save(out, format="JPEG")

    return out.getvalue()


def _image(tmp_path, runner, reading, raw=None, mimetype="image/jpeg", caption=""):
    """Roda CoachMediaMessage.image com storage no tmp e coach/plano mockados."""

    media = ChatMediaStore()
    media.storage = tmp_path / "chat_media"

    conv = ConversationRepository()
    conv.storage = tmp_path / "conv"
    conv.storage.mkdir(exist_ok=True)

    coach = AsyncMock(return_value="resposta do coach")
    plan = AsyncMock(return_value="Plano do seu treinador registrado!")

    with (
        patch(f"{MOD}.LoadRunnerProfile.execute", return_value=runner),
        patch(f"{MOD}.ChatMediaStore", return_value=media),
        patch(f"{MOD}.ConversationRepository", return_value=conv),
        patch(f"{MOD}.InboundImageReader.read", new=AsyncMock(return_value=reading)),
        patch(f"{MOD}.CoachConversationEvent.execute", new=coach),
        patch(f"{MOD}.ExternalPlanEvent.execute", new=plan),
        patch(f"{MOD}.NotificationService.send", new=AsyncMock()),
    ):

        reply = asyncio.run(
            CoachMediaMessage.image(
                "renato2",
                raw if raw is not None else _jpeg(),
                mimetype,
                caption=caption,
                notify=False,
            )
        )

    return reply, coach, plan, media, conv


def test_photo_goes_to_coach_pipeline_with_description_and_attachment(tmp_path):

    reading = {"kind": "workout", "description": "Print do Strava: 10 km em 52:10."}

    reply, coach, plan, media, _ = _image(
        tmp_path, make_runner(), reading, caption="olha meu treino de ontem",
    )

    assert reply == "resposta do coach"
    plan.assert_not_awaited()

    kwargs = coach.await_args.kwargs

    # o coach LÊ a legenda + o que a foto mostra
    assert "olha meu treino de ontem" in kwargs["incoming_text"]
    assert "10 km em 52:10" in kwargs["incoming_text"]
    assert "registro de treino" in kwargs["incoming_text"]

    # o app MOSTRA a legenda + a foto guardada
    assert kwargs["display_text"] == "olha meu treino de ontem"
    assert kwargs["attachment"]["type"] == "image"
    assert media.path("renato2", kwargs["attachment"]["id"]) is not None
    assert kwargs["notify"] is False


def test_external_coach_plan_screenshot_registers_plan_and_records_turns(tmp_path):

    reading = {"kind": "training_plan", "description": "Planilha da semana."}

    reply, coach, plan, _, conv = _image(
        tmp_path, make_runner(external_coach=True), reading,
    )

    assert reply.startswith("Plano do seu treinador registrado")
    coach.assert_not_awaited()
    assert plan.await_args.kwargs["notify"] is False

    turns = conv.load("renato2")

    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["attachment"]["type"] == "image"
    assert turns[0]["display_text"] == ""


def test_external_coach_non_plan_photo_still_talks_to_coach(tmp_path):
    """Treina com treinador, mas mandou foto do pé inchado: é conversa, não plano."""

    reading = {"kind": "other", "description": "Tornozelo direito inchado."}

    _, coach, plan, _, _ = _image(
        tmp_path, make_runner(external_coach=True), reading, caption="tá doendo",
    )

    plan.assert_not_awaited()
    coach.assert_awaited_once()


def test_unreadable_photo_without_caption_answers_honestly(tmp_path):

    reply, coach, _, _, conv = _image(tmp_path, make_runner(), None)

    assert reply == UNSEEN_IMAGE_REPLY
    coach.assert_not_awaited()
    assert conv.load("renato2")[-1]["text"] == UNSEEN_IMAGE_REPLY


def test_unreadable_photo_with_caption_keeps_the_conversation(tmp_path):

    _, coach, _, _, _ = _image(tmp_path, make_runner(), None, caption="e aí?")

    text = coach.await_args.kwargs["incoming_text"]

    assert text.startswith("e aí?")
    assert "não pôde ser lida" in text


def test_garbage_bytes_are_not_an_image(tmp_path):

    reply, coach, _, _, _ = _image(
        tmp_path, make_runner(), {"kind": "other", "description": "x"}, raw=b"nope",
    )

    assert reply == UNOPENABLE_IMAGE_REPLY
    coach.assert_not_awaited()


def test_voice_transcribes_and_follows_the_conversation():

    with (
        patch(f"{MOD}.VoiceTranscriber.transcribe", new=AsyncMock(return_value="fiz 8 km leve")),
        patch(f"{MOD}.CoachConversationEvent.execute", new=AsyncMock(return_value="boa!")) as coach,
    ):

        out = asyncio.run(
            CoachMediaMessage.voice("renato2", b"audio", 12, notify=False)
        )

    assert out == {"transcript": "fiz 8 km leve", "reply": "boa!"}

    kwargs = coach.await_args.kwargs

    assert kwargs["incoming_text"] == "fiz 8 km leve"
    assert kwargs["display_text"] == "🎤 fiz 8 km leve"
    assert kwargs["notify"] is False


def test_voice_too_long_or_silent_never_goes_silent():

    with patch(f"{MOD}.VoiceTranscriber.transcribe", new=AsyncMock(return_value="")) as tr:

        too_long = asyncio.run(CoachMediaMessage.voice("renato2", b"a", 99999))
        silent = asyncio.run(CoachMediaMessage.voice("renato2", b"a", 5))

    assert too_long == {"transcript": None, "reply": VOICE_TOO_LONG_REPLY}
    assert silent == {"transcript": None, "reply": VOICE_UNHEARD_REPLY}
    assert tr.await_count == 1


def test_compose_without_caption_is_only_the_note():

    text = compose_image_text({"kind": "other", "description": "Tênis novo."}, "")

    assert text.startswith("[📷 Foto enviada pelo atleta — imagem: Tênis novo.")


# ---------------------------------------------------------------- API

def _client(profile="renato2"):

    client = TestClient(app)

    client.cookies.set("rm_session", SessionToken.issue(profile))

    return client


def test_photo_endpoint_decodes_data_url_and_calls_media_service():

    data = "data:image/jpeg;base64," + base64.b64encode(_jpeg()).decode()

    with patch(
        f"{API}.CoachMediaMessage.image",
        new=AsyncMock(return_value="vi sua foto"),
    ) as image:

        r = _client().post("/api/v1/coach/photo", json={"data": data, "caption": "oi"})

    assert r.status_code == 200
    assert r.json() == {"reply": "vi sua foto"}

    args, kwargs = image.await_args

    assert args[0] == "renato2"
    assert args[2] == "image/jpeg"
    assert kwargs == {"caption": "oi", "notify": False}


def test_photo_endpoint_rejects_non_image_and_requires_login():

    r = _client().post(
        "/api/v1/coach/photo", json={"data": "data:video/mp4;base64,AAAA"},
    )

    assert r.status_code == 415

    r = TestClient(app).post("/api/v1/coach/photo", json={"data": "x"})

    assert r.status_code == 401


def test_voice_endpoint_returns_transcript_and_reply():

    data = "data:audio/webm;base64," + base64.b64encode(b"som").decode()

    with patch(
        f"{API}.CoachMediaMessage.voice",
        new=AsyncMock(return_value={"transcript": "oi", "reply": "fala!"}),
    ):

        r = _client().post("/api/v1/coach/voice", json={"data": data, "duration": 3})

    assert r.json() == {"transcript": "oi", "reply": "fala!"}


def test_media_endpoint_serves_only_own_photo(tmp_path):

    store = ChatMediaStore()
    store.storage = tmp_path / "chat_media"

    media_id, _ = store.save_image("renato2", _jpeg())

    with patch(f"{API}.ChatMediaStore", return_value=store):

        ok = _client().get(f"/api/v1/coach/media/{media_id}")
        bad_id = _client().get("/api/v1/coach/media/nao-e-um-id")
        foreign = _client("outro").get(f"/api/v1/coach/media/{media_id}")

    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/jpeg"
    assert bad_id.status_code == 404
    assert foreign.status_code == 404


def test_timeline_shows_caption_and_photo_instead_of_the_description(tmp_path):

    conv = ConversationRepository()
    conv.storage = tmp_path

    conv.append_turn(
        "renato2",
        "user",
        "legenda\n\n[📷 Foto ... descrição longa]",
        display_text="legenda",
        attachment={"type": "image", "id": MEDIA_ID},
    )

    with (
        patch(f"{API}.ConversationRepository", return_value=conv),
        patch(f"{API}.AppNotificationRepository") as notif,
    ):

        notif.return_value.load.return_value = []

        msgs = _client().get("/api/v1/coach/messages").json()["messages"]

    assert msgs[-1]["text"] == "legenda"
    assert msgs[-1]["image_url"] == f"/api/v1/coach/media/{MEDIA_ID}"

    stored = json.loads((tmp_path / "renato2.json").read_text("utf-8"))[-1]

    # o coach continua lendo tudo
    assert "descrição longa" in stored["text"]
