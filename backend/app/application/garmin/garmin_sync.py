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
from app.infrastructure.integrations.garmin.foreign_workout_store import (
    ForeignWorkoutStore,
)
from app.infrastructure.integrations.garmin.garmin_offer_store import (
    GarminOfferStore,
)

# OK pra apagar os treinos de FORA do Ritmind que o coach acabou de apontar
_REMOVE_FOREIGN = re.compile(
    r"\b(apaga|apagar|apague|tira|tirar|tire|remove|remover|exclui|excluir|deleta|deletar)\b"
)

# "sim" curto só vale pra remoção quando NÃO há oferta de relógio pendente
_REMOVE_FOREIGN_SHORT = {"sim", "s", "pode", "pode sim", "ok", "isso", "claro", "yes", "bora"}

_WEEKDAY_PT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def _when(iso: str) -> str:

    from datetime import date

    on = date.fromisoformat(iso)

    return f"{_WEEKDAY_PT[on.weekday()]} {on:%d/%m}"


def foreign_note(items: list[dict], from_app: bool = False) -> str:
    """Aviso honesto dos treinos de FORA do Ritmind no relógio: reenviar não
    apaga eles (não são nossos), então diz quais são e pergunta."""

    lines = "\n".join(f"• {i['title']} ({_when(i['date'])})" for i in items)

    return (
        "⚠️ Teu Garmin também tem treino(s) que NÃO são do Ritmind nesta semana — "
        "por isso o relógio parece ter treino a mais:\n\n"
        f"{lines}\n\n"
        "Reenviar não mexe neles (podem ser teus ou de outro app). "
        "Quer que eu apague? Responde *pode apagar*"
        + (" no chat comigo." if from_app else ".")
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


def _wants_foreign_removed(norm: str, offer_pending: bool) -> bool:
    """O atleta autorizou apagar os treinos de fora apontados? "pode apagar",
    "apaga eles", "tira os duplicados"… Frase com verbo de remover precisa ser
    curta ou falar DELES — "tira o treino de quinta" é outra coisa (mexe no
    plano). Um "sim" solto só conta se não há oferta de relógio pendente."""

    if norm.startswith("nao"):

        return False

    if norm in _REMOVE_FOREIGN_SHORT:

        return not offer_pending

    if not _REMOVE_FOREIGN.search(norm):

        return False

    about_them = re.search(
        r"\b(eles|elas|esses|essas|todos|duplicad\w*|repetid\w*|de fora|garmin|relogio|isso)\b",
        norm,
    )

    return bool(about_them) or len(norm.split()) <= 3


class GarminSync:

    @staticmethod
    def should_offer(profile: str, runner: RunnerProfile) -> bool:
        """Oferece só quando o plano é do Ritmind e o atleta conectou o
        Garmin. Atleta com treinador externo já recebe os treinos pela
        ferramenta do treinador — não duplicamos no relógio."""

        if getattr(runner, "external_coach", False):

            return False

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

        # atleta com treinador externo recebe os treinos pela ferramenta
        # do treinador — o push do Ritmind não se aplica a ele
        if getattr(runner, "external_coach", False):

            return None

        norm = _normalize(incoming_text)

        pending = GarminOfferStore.is_pending(profile)

        # resposta ao aviso de treinos de FORA do Ritmind no relógio
        foreign = ForeignWorkoutStore.pending(profile)

        if foreign:

            if _wants_foreign_removed(norm, offer_pending=pending):

                return await GarminSync._remove_foreign(profile, foreign)

            if not pending and norm in _NEGATIVE:

                ForeignWorkoutStore.clear(profile)

                return "Beleza, deixo esses treinos como estão no teu Garmin. 👍"

        explicit = any(rx.search(norm) for rx in _EXPLICIT_REGEXES)

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
    async def _remove_foreign(profile: str, items: list[dict]) -> str:
        """Apaga do Garmin os treinos de fora que o atleta AUTORIZOU. Confere
        id + nome na biblioteca antes de apagar (se ele já mexeu, pula) e diz
        exatamente o que saiu — nunca "apaguei" sem ter apagado."""

        import asyncio

        def _run() -> tuple[list[str], list[str]]:

            garmin = GarminClient.connect(profile)

            library = {
                w.get("workoutId"): w.get("workoutName") or ""
                for w in garmin.get_workouts(0, 100)
            }

            removed, failed = [], []

            for item in items:

                if library.get(item["workout_id"]) != item["title"]:

                    continue  # já não está lá (ou mudou): não mexe

                try:

                    garmin.delete_workout(item["workout_id"])

                    removed.append(item["title"])

                except Exception as e:  # noqa: BLE001 — um por vez

                    print(f"Falha ao apagar treino de fora {item}: {e}")

                    failed.append(item["title"])

            return removed, failed

        try:

            removed, failed = await asyncio.to_thread(_run)

        except Exception as e:

            print(f"Falha ao apagar treinos de fora de '{profile}': {e}")

            return (
                "Tentei apagar esses treinos do teu Garmin mas deu problema agora 😕 "
                "Me fala *pode apagar* de novo daqui a pouco."
            )

        if failed:

            return (
                (f"Apaguei: {', '.join(removed)}. " if removed else "")
                + f"Não consegui apagar: {', '.join(failed)} — tenta *pode apagar* "
                "de novo daqui a pouco."
            )

        ForeignWorkoutStore.clear(profile)

        if not removed:

            return "Esses treinos já não estão mais no teu Garmin. ⌚"

        return (
            f"Pronto, apaguei do teu Garmin: {', '.join(removed)}. Agora só ficam "
            "os treinos do Ritmind — sincroniza o relógio. ⌚"
        )

    @staticmethod
    async def _push(
        profile: str,
        runner: RunnerProfile,
    ) -> str:
        """Manda a semana pro relógio e responde com o resultado REAL. Se o
        relógio tem treinos de FORA do Ritmind na semana, diz quais são e
        pergunta se apaga (reenviar não resolve "treino a mais")."""

        foreign: list[dict] = []

        reply = await GarminSync._push_reply(profile, runner, foreign)

        if foreign:

            ForeignWorkoutStore.set_pending(profile, foreign)

            return f"{reply}\n\n{foreign_note(foreign)}"

        ForeignWorkoutStore.clear(profile)

        return reply

    @staticmethod
    async def _push_reply(
        profile: str,
        runner: RunnerProfile,
        foreign: list[dict],
    ) -> str:

        GarminOfferStore.clear(profile)

        if not GarminClient.is_connected(profile):

            return (
                "Opa, seu Garmin não está conectado por aqui ainda. "
                "Quando conectar, eu mando os treinos pro relógio. ⌚"
            )

        try:

            _, _, results = await push_current_plan(profile, foreign_out=foreign)

        except Exception as e:

            print(f"Falha ao sincronizar Garmin de '{profile}': {e}")

            return (
                "Tentei mandar pro seu Garmin mas deu um problema agora 😕 "
                "Me chama daqui a pouco que eu tento de novo."
            )

        sent = [r for r in results if r.get("ok")]

        from app.application.garmin.watch_day import LATE_TODAY_NOTE

        late = any(r.get("action") == "late_today" for r in results)

        if late and not sent:

            return f"{runner.name}, {LATE_TODAY_NOTE}"

        if not results:

            # nada pela frente pra agendar (a semana acabou ou o que faltava
            # saiu do plano) — o push já limpou do relógio o que saiu. Não é
            # falha: antes dizia "não consegui agendar" (Renato 27/09, depois de
            # cancelar o último treino da semana)
            return (
                "⌚ Relógio em dia! Desta semana não sobrou treino pra agendar — "
                "o que saiu do plano saiu do relógio também."
            )

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
            "Treino → Programados, cada um agendado no seu dia. "
            "Bons treinos! 🏃"
            + (f"\n\nSó o de hoje: {LATE_TODAY_NOTE}" if late else "")
        )
