"""Broadcast de INFORMATIVO pros atletas — o "novidades" curado.

Regra de ouro: NÃO é automático por commit. A maioria das mudanças é invisível
pro atleta (plumbing, refactor); ele só liga pro "o que muda pra MIM". Então
isto é disparado À MÃO, quando há algo athlete-facing de verdade — raro e
valioso > frequente e ruidoso.

Garantias: dedup por (announcement_id, atleta) via DispatchGuard — rodar duas
vezes não manda duas; best-effort — um atleta que falha não trava os outros;
`only` permite testar num atleta antes de mandar pra todos. Personaliza "{name}"
quando presente no texto. Ver [[project_ideias_produto]]."""

from app.application.notifications.coach_outbox import CoachOutbox
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

_KIND = "announcement"


class AnnouncementBroadcaster:

    @staticmethod
    async def broadcast(
        announcement_id: str,
        message: str,
        only: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Manda o informativo pros atletas ativos. `announcement_id` é a chave
        de dedup (ex.: '2026-07-retrato'); `only` restringe a alguns perfis
        (teste); `dry_run` não envia nem marca — só devolve quem receberia.

        Devolve {'sent', 'skipped', 'failed', 'preview'} pra inspeção."""

        profiles = only or RunnerProfileRepository().list_all()

        result: dict = {
            "sent": [],
            "skipped": [],
            "failed": [],
            "preview": {},
        }

        for profile in profiles:

            try:

                if DispatchGuard.already_sent(_KIND, profile, announcement_id):

                    result["skipped"].append(profile)

                    continue

                runner = LoadRunnerProfile.execute(profile)

                text = AnnouncementBroadcaster._personalize(message, runner)

                if dry_run:

                    result["preview"][profile] = text

                    continue

                await CoachOutbox.send(
                    runner, text, profile=profile, kind="announcement",
                )

                # marca só APÓS enviar com sucesso (falha não vira "já enviado")
                DispatchGuard.mark(_KIND, profile, announcement_id)

                result["sent"].append(profile)

            except Exception as e:  # noqa: BLE001 — um atleta não derruba os outros

                result["failed"].append((profile, str(e)))

        return result

    @staticmethod
    def _personalize(message: str, runner) -> str:
        """Troca '{name}' pelo nome do atleta quando o template usa. Sem o
        placeholder, o texto é genérico (vale pra todos)."""

        name = getattr(runner, "name", "") or ""

        return message.replace("{name}", name) if "{name}" in message else message
