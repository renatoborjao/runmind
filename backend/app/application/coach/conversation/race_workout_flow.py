"""Oferta "quer a prova como treino no relógio?" + o "sim" que a executa.

O companheiro de prova (semana da prova) faz a oferta e arma o pendente; aqui a
gente lê a resposta: SIM empurra o treino de prova guiado pro Garmin (via
[[push_race_workout]], protegido do sweep), NÃO encerra. Determinístico, roda
antes do Gemini — igual ao fluxo do avulso ([[OneOffWorkoutFlow]])."""

import re
import unicodedata

from app.application.garmin.push_race_workout import push_race_workout
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.race_workout_offer_store import (
    RaceWorkoutOfferStore,
)

_AFFIRMATIVE = {
    "sim", "s", "quero", "quero sim", "pode", "pode ser", "isso", "bora",
    "manda", "claro", "ok", "aceito", "pode mandar", "sim quero", "manda ai",
    "manda ver", "sim!", "quero!", "bora!",
}

_NEGATIVE = {
    "nao", "nao quero", "agora nao", "depois", "deixa", "nao precisa",
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


class RaceWorkoutFlow:

    @staticmethod
    def offer_text() -> str:

        return (
            "\n\n⌚ Quer que eu mande a estratégia como TREINO GUIADO pro teu "
            "relógio? Ele mostra o pace-alvo de cada trecho e te segura no "
            "começo (o segredo pra não quebrar). Responde *SIM* que eu mando."
        )

    @staticmethod
    def eligible(
        profile: str, runner: RunnerProfile, race_iso: str | None = None,
    ) -> bool:
        """Só oferece quando dá pra empurrar: Garmin conectado, plano nosso
        (treinador externo recebe pela ferramenta dele) E a prova ainda NÃO
        foi mandada pro relógio (senão o coach re-ofereceria algo que já está
        lá — a queixa do Renato)."""

        if getattr(runner, "external_coach", False):

            return False

        if race_iso and RaceWorkoutOfferStore.already_sent(profile, race_iso):

            return False

        return GarminClient.is_connected(profile)

    @staticmethod
    async def resolve_watch_reply(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:
        """SIM à oferta de prova → empurra o treino; NÃO → encerra; sem oferta
        pendente ou resposta ambígua → None (a conversa segue)."""

        if getattr(runner, "external_coach", False):

            return None

        if not RaceWorkoutOfferStore.is_pending(profile):

            return None

        norm = _normalize(incoming_text)

        if norm in _NEGATIVE:

            RaceWorkoutOfferStore.clear(profile)

            return (
                "Tranquilo! Se mudar de ideia, é só falar 'manda a prova pro "
                "relógio'. 👍"
            )

        if norm not in _AFFIRMATIVE:

            return None  # resposta ambígua: deixa a conversa seguir

        RaceWorkoutOfferStore.clear(profile)

        return await RaceWorkoutFlow._push(profile, runner)

    @staticmethod
    async def _push(profile: str, runner: RunnerProfile) -> str:

        if not GarminClient.is_connected(profile):

            return (
                "Opa, teu Garmin não está conectado por aqui ainda. Quando "
                "conectar, eu mando a prova pro relógio. ⌚"
            )

        try:

            result = await push_race_workout(profile)

        except Exception as e:

            print(f"Falha ao empurrar prova pro Garmin de '{profile}': {e}")

            return (
                "Tentei mandar a prova pro teu relógio mas deu um problema "
                "agora 😕 Me chama daqui a pouco que eu tento de novo."
            )

        if not result or not result.get("ok"):

            return (
                "Não consegui montar/agendar a prova no relógio agora 😕 Me "
                "chama mais tarde que a gente tenta de novo."
            )

        return (
            f"Pronto, {runner.name}! ⌚ Mandei a prova como treino guiado pro "
            f"teu Garmin (agendada {result['date']}). Aparece em Treino → "
            "Treinos. No dia, o relógio te guia o pace de cada trecho e te "
            "alerta se acelerar cedo demais. Bora! 🏁"
        )
