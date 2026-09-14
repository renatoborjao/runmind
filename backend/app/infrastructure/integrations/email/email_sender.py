from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import get_settings


class EmailSender:
    """Envia e-mail por SMTP (stdlib, sem dependência). Grátis com Gmail +
    app password (smtp.gmail.com:587).

    Modo DEV: quando `smtp_host` está vazio, NÃO envia — imprime o assunto e o
    corpo no log. Assim dá pra testar o fluxo de login inteiro sem configurar
    e-mail. Falha de envio nunca quebra o fluxo: loga e segue (o chamador não
    revela ao usuário se o e-mail existe ou não)."""

    @staticmethod
    def send(to: str, subject: str, body_text: str, body_html: str | None = None) -> bool:

        settings = get_settings()

        if not settings.smtp_host:

            print("=" * 60)
            print(f"[EMAIL DEV] para: {to}")
            print(f"[EMAIL DEV] assunto: {subject}")
            print(f"[EMAIL DEV] corpo:\n{body_text}")
            print("=" * 60)

            return True

        try:

            msg = EmailMessage()

            from_addr = settings.smtp_from or settings.smtp_user

            msg["From"] = formataddr((settings.smtp_from_name, from_addr))
            msg["To"] = to
            msg["Subject"] = subject

            msg.set_content(body_text)

            if body_html:

                msg.add_alternative(body_html, subtype="html")

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:

                smtp.starttls()

                if settings.smtp_user:

                    smtp.login(settings.smtp_user, settings.smtp_password)

                smtp.send_message(msg)

            return True

        except Exception as e:

            print(f"[EMAIL] falha ao enviar para '{to}': {e}")

            return False
