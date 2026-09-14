from __future__ import annotations

import json

from app.core.config import get_settings
from app.infrastructure.persistence.push_subscription_repository import (
    PushSubscriptionRepository,
)


class WebPushSender:
    """Envia Web Push (notificação que aparece no celular MESMO com o app
    fechado) pras inscrições do atleta. Usa VAPID (par de chaves nosso) +
    criptografia RFC 8291 via `pywebpush`.

    Tudo aqui é BEST-EFFORT: sem chaves VAPID configuradas, ou sem a lib, ou o
    push service fora do ar -> não faz nada e NUNCA levanta exceção (a mensagem
    já saiu no Telegram e na central do app). Inscrição morta (404/410) é
    removida sozinha, pra não tentar de novo eternamente."""

    @staticmethod
    def _configured() -> bool:

        s = get_settings()

        return bool(s.vapid_private_key and s.vapid_public_key)

    @staticmethod
    def send(profile: str, title: str, body: str, url: str = "/inicio") -> None:
        """Dispara o push pra todos os aparelhos do atleta. Silencioso."""

        if not WebPushSender._configured():

            return

        try:

            from pywebpush import WebPushException, webpush

        except Exception:

            # lib ausente (ex.: ambiente de teste sem a dependência): sem push
            return

        settings = get_settings()

        repo = PushSubscriptionRepository()

        subs = repo.list(profile)

        if not subs:

            return

        payload = json.dumps({
            "title": title or "Ritmind",
            "body": body or "",
            "url": url or "/inicio",
        })

        claims = {"sub": settings.vapid_subject}

        for sub in subs:

            endpoint = sub.get("endpoint")

            if not endpoint:

                continue

            try:

                webpush(
                    subscription_info={
                        "endpoint": endpoint,
                        "keys": sub.get("keys") or {},
                    },
                    data=payload,
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims=dict(claims),
                    ttl=60 * 60 * 24,
                )

            except WebPushException as e:

                status = getattr(getattr(e, "response", None), "status_code", None)

                # inscrição expirada/removida no aparelho: limpa pra não insistir
                if status in (404, 410):

                    try:

                        repo.remove(profile, endpoint)

                    except Exception:

                        pass

                else:

                    print(f"[webpush] falha p/ '{profile}' ({status}): {e}")

            except Exception as e:

                print(f"[webpush] erro inesperado p/ '{profile}': {e}")
