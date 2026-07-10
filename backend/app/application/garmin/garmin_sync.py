"""Fluxo opt-in do Garmin na conversa: o plano é entregue com a pergunta
"quer no relógio?"; se o atleta responde SIM (ou pede explicitamente a
qualquer momento), sincroniza os treinos da semana pro Garmin dele.

Determinístico (roda antes do Gemini) — igual às outras intenções canônicas."""

import re
import unicodedata

from app.application.garmin.push_current_plan import push_current_plan
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)
from app.infrastructure.integrations.garmin.garmin_offer_store import (
    GarminOfferStore,
)

# pedido EXPLÍCITO de sincronizar (vale a qualquer momento, sem oferta ativa)
_EXPLICIT_REGEXES = [
    re.compile(r"\b(manda|poe|poem|coloca|joga|sincroniza|envia|passa|bota)\b"
               r".*\b(garmin|relogio)\b"),
    re.compile(r"\b(garmin|relogio)\b.*\b(manda|poe|sincroniza|envia|quero)\b"),
    re.compile(r"\bquero\b.*\b(no|pro|para o)\b.*\b(garmin|relogio)\b"),
]

# respostas afirmativas curtas (só contam quando há oferta pendente)
_AFFIRMATIVE = {
    "sim", "s", "quero", "quero sim", "pode", "pode ser", "isso", "bora",
    "manda", "claro", "ok", "aceito", "sim quero", "pode mandar", "yes",
    "sim!", "quero!", "bora!", "manda ai", "manda ver",
}

_NEGATIVE = {
    "nao", "nao quero", "agora nao", "depois", "deixa", "nem", "nao precisa",
    "pode deixar", "nao obrigado",
}


def _normalize(text: str) -> str:

    lowered = (text or "").lower().strip()

    without = "".join(
        c
        for c in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(c) != "Mn"
    )

    return re.sub(r"\s+", " ", without)


class GarminSync:

    @staticmethod
    def should_offer(profile: str) -> bool:
        """Só oferece se o atleta conectou o Garmin."""

        return GarminClient.is_connected(profile)

    @staticmethod
    def offer_text() -> str:

        return (
            "\n\n⌚ Vi que você tem Garmin conectado! Quer esses treinos "
            "direto no seu relógio? Responda *SIM* que eu já mando."
        )

    @staticmethod
    async def handle_reply(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:
        """Se a mensagem for aceite da oferta ou pedido explícito de
        sincronizar, empurra o plano e responde. Senão devolve None (a
        conversa segue normal)."""

        norm = _normalize(incoming_text)

        explicit = any(rx.search(norm) for rx in _EXPLICIT_REGEXES)

        pending = GarminOfferStore.is_pending(profile)

        if not explicit and not pending:

            return None

        # havia oferta e o atleta recusou: encerra sem sincronizar
        if pending and not explicit and norm in _NEGATIVE:

            GarminOfferStore.clear(profile)

            return (
                "Beleza! Se mudar de ideia, é só falar "
                "'manda pro Garmin'. 👍"
            )

        accepted = explicit or (pending and norm in _AFFIRMATIVE)

        if not accepted:

            # com oferta pendente mas resposta ambígua: deixa o Gemini tratar
            return None

        return await GarminSync._push(profile, runner)

    @staticmethod
    async def _push(
        profile: str,
        runner: RunnerProfile,
    ) -> str:

        GarminOfferStore.clear(profile)

        if not GarminClient.is_connected(profile):

            return (
                "Opa, seu Garmin não está conectado por aqui ainda. "
                "Quando conectar, eu mando os treinos pro relógio. ⌚"
            )

        try:

            _, _, results = await push_current_plan(profile)

        except Exception as e:

            print(f"Falha ao sincronizar Garmin de '{profile}': {e}")

            return (
                "Tentei mandar pro seu Garmin mas deu um problema agora 😕 "
                "Me chama daqui a pouco que eu tento de novo."
            )

        sent = [r for r in results if r.get("ok")]

        if not sent:

            return (
                "Não consegui agendar os treinos no seu Garmin agora 😕 "
                "Me chama mais tarde que a gente tenta de novo."
            )

        lines = "\n".join(
            f"• {r['workout']} ({r['date']})" for r in sent
        )

        return (
            f"Pronto, {runner.name}! ⌚ Mandei pro seu Garmin:\n\n"
            f"{lines}\n\n"
            "É só sincronizar o relógio com o app que eles aparecem em "
            "Treino → Treinos. Bons treinos! 🏃"
        )
