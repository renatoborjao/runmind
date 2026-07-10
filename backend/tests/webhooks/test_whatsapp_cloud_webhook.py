import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

MODULE = "app.presentation.api.v1.webhooks"

client = TestClient(app)


def _inbound_payload(body: str = "oi coach") -> dict:

    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"profile": {"name": "Renato"}}
                            ],
                            "messages": [
                                {
                                    "from": "5511976483800",
                                    "id": "wamid.X",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_get_verification_echoes_challenge():

    with patch(f"{MODULE}.get_settings") as mock_settings:

        mock_settings.return_value.whatsapp_verify_token = "segredo123"

        r = client.get(
            "/api/v1/webhooks/whatsapp-cloud",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "segredo123",
                "hub.challenge": "42",
            },
        )

        assert r.status_code == 200
        assert r.text == "42"


def test_get_verification_rejects_wrong_token():

    with patch(f"{MODULE}.get_settings") as mock_settings:

        mock_settings.return_value.whatsapp_verify_token = "segredo123"

        r = client.get(
            "/api/v1/webhooks/whatsapp-cloud",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "errado",
                "hub.challenge": "42",
            },
        )

        assert r.status_code == 403


def test_post_routes_inbound_message():

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.route_inbound", new_callable=AsyncMock) as mock_route,
    ):

        # sem app secret: assinatura não bloqueia (teste local)
        mock_settings.return_value.whatsapp_app_secret = ""

        mock_route.return_value = {"success": True, "reply_sent": True}

        r = client.post(
            "/api/v1/webhooks/whatsapp-cloud",
            json=_inbound_payload("bom dia"),
        )

        assert r.status_code == 200

        mock_route.assert_awaited_once()
        kwargs = mock_route.await_args.kwargs
        assert kwargs["channel"] == "whatsapp"
        assert kwargs["address"] == "5511976483800"
        assert kwargs["text"] == "bom dia"
        assert kwargs["sender_name"] == "Renato"


def test_post_rejects_bad_signature():

    with patch(f"{MODULE}.get_settings") as mock_settings:

        mock_settings.return_value.whatsapp_app_secret = "APPSECRET"

        r = client.post(
            "/api/v1/webhooks/whatsapp-cloud",
            json=_inbound_payload(),
            headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        )

        assert r.status_code == 403


def test_post_accepts_valid_signature():

    payload = _inbound_payload("assinado")

    raw = json.dumps(payload).encode()

    sig = hmac.new(b"APPSECRET", raw, hashlib.sha256).hexdigest()

    with (
        patch(f"{MODULE}.get_settings") as mock_settings,
        patch(f"{MODULE}.route_inbound", new_callable=AsyncMock) as mock_route,
    ):

        mock_settings.return_value.whatsapp_app_secret = "APPSECRET"
        mock_route.return_value = {"success": True}

        r = client.post(
            "/api/v1/webhooks/whatsapp-cloud",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={sig}",
            },
        )

        assert r.status_code == 200
        mock_route.assert_awaited_once()


def test_post_ignores_status_only_payload():

    status_payload = {
        "entry": [
            {"changes": [{"value": {"statuses": [{"status": "read"}]}}]}
        ]
    }

    with patch(f"{MODULE}.get_settings") as mock_settings:

        mock_settings.return_value.whatsapp_app_secret = ""

        r = client.post(
            "/api/v1/webhooks/whatsapp-cloud",
            json=status_payload,
        )

        assert r.status_code == 200
        assert r.json()["ignored"] is True
