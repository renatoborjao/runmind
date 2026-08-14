"""Ponto único do check-in de sensação: captura reativa (detector + extrator +
gravação) e renderização do estado recente pra injetar no cérebro do coach
(geração de plano e conversa). Ver [[project_ideias_produto]] item 4."""

from app.application.coach.intelligence.checkin_extractor import (
    CheckinDetector,
    CheckinExtractor,
)
from app.core.clock import now_local, today_local
from app.domain.entities.daily_checkin import DailyCheckin
from app.infrastructure.persistence.checkin_repository import CheckinRepository

_ENERGY = {1: "exausto", 2: "baixa", 3: "normal", 4: "boa", 5: "alta"}
_SLEEP = {1: "péssimo", 2: "ruim", 3: "ok", 4: "bom", 5: "ótimo"}
# dor 1 = sem queixa: não é ponto de atenção, sai do render
_SORE = {2: "leve", 3: "moderada", 4: "considerável", 5: "forte"}


class CheckinService:

    @staticmethod
    async def capture(
        profile: str, runner_name: str, incoming_text: str
    ) -> DailyCheckin | None:
        """Se a mensagem relata sensação, extrai e grava o check-in do dia.
        Best-effort — o chamador embrulha em try/except. None se nada a captar."""

        if not CheckinDetector.mentions_state(incoming_text):

            return None

        checkin = await CheckinExtractor.extract(
            runner_name=runner_name,
            incoming_text=incoming_text,
            day=today_local().isoformat(),
            at=now_local().isoformat(),
        )

        if checkin is None:

            return None

        CheckinRepository().record(profile, checkin)

        return checkin

    @staticmethod
    def render_recent(profile: str) -> str:
        """Estado subjetivo recente do atleta pro contexto do coach; string
        vazia quando não há relato recente (não injeta nada)."""

        checkin = CheckinRepository().latest_recent(
            profile, today_local().isoformat()
        )

        if checkin is None:

            return ""

        return CheckinService.render(checkin)

    @staticmethod
    def render(checkin: DailyCheckin) -> str:

        parts = []

        # doença primeiro — é o sinal mais forte pra dose do dia
        if checkin.illness:

            parts.append("relatou estar DOENTE (gripe/resfriado/febre)")

        if checkin.energy is not None:

            parts.append(f"energia {_ENERGY.get(checkin.energy, checkin.energy)}")

        if checkin.sleep_quality is not None:

            parts.append(f"sono {_SLEEP.get(checkin.sleep_quality, checkin.sleep_quality)}")

        if checkin.soreness is not None and checkin.soreness >= 2:

            parts.append(f"dor {_SORE[checkin.soreness]}")

        if checkin.note:

            parts.append(checkin.note)

        if not parts:

            return ""

        return (
            "Estado que o atleta RELATOU sentir (leve em conta na dose): "
            + ", ".join(parts)
            + "."
        )
