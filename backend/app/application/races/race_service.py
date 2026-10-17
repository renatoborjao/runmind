"""Provas do atleta pelo app: cadastrar uma ou VÁRIAS, listar e remover — sem
quebrar a periodização, que continua ancorada na prova datada MAIS PRÓXIMA pelos
campos do perfil (target_race/race_date/target_time).

O RaceService é a cola: a lista estruturada mora no [[RaceRepository]]; a cada
mudança ele recomputa a âncora do perfil (a prova futura mais próxima) e, ao
adicionar, registra na memória evolutiva (o coach passa a equilibrar a prova no
plano — [[project_multiplos_objetivos]]). Na leitura, reconcilia a prova que o
coach setou por conversa (importa pra lista), pra os dois lados baterem."""

from __future__ import annotations

from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.core.clock import today_local
from app.domain.value_objects.race_distance import parse_race_distance
from app.infrastructure.persistence.race_repository import RaceRepository
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# papel da prova no ciclo: define o quanto o plano se organiza em torno dela
PRIORITIES = ("A", "B", "C")

PRIORITY_LABELS = {
    "A": "principal",
    "B": "preparatória",
    "C": "de treino",
}


class RaceService:

    @staticmethod
    def list(profile: str) -> list[dict]:
        """Provas do atleta, da mais próxima pra mais distante, com `is_anchor`
        marcando a que ancora o plano (a próxima futura). Reconcilia a prova que
        o coach cadastrou por conversa (importa pra lista, se faltava)."""

        repo = RaceRepository()

        races = repo.load(profile)

        RaceService._import_profile_anchor(profile, repo, races)

        races = repo.load(profile)

        today = today_local().isoformat()

        # âncora = prova futura mais próxima (a periodização usa esta)
        future = sorted(
            (r for r in races if r.get("date") and r["date"] >= today),
            key=lambda r: r["date"],
        )

        anchor_id = future[0]["id"] if future else None

        out = sorted(races, key=lambda r: r.get("date") or "9999")

        for r in out:

            r["is_anchor"] = r.get("id") == anchor_id

            r["past"] = bool(r.get("date") and r["date"] < today)

            # distância: a guardada ou a que o nome entrega (nunca grava na leitura)
            stored_km = r.get("distance_km")

            r["distance_inferred"] = not stored_km

            # forma estável da API: prova antiga ainda não tem o campo
            r.setdefault("priority", None)

            r["distance_km"] = stored_km or parse_race_distance(r.get("name"))

        suggested = RaceService._suggest_priorities(out, today)

        for r in out:

            r["priority_suggested"] = suggested.get(r.get("id"))

            # papel EFETIVO = o que o atleta escolheu, senão o sugerido
            r["priority_effective"] = r.get("priority") or r["priority_suggested"]

        return out

    @staticmethod
    def _suggest_priorities(races: list[dict], today: str) -> dict[str, str]:
        """Sugestão de papel pra quem ainda não escolheu (o atleta confirma ou
        troca na tela): prova única à frente = principal; com várias, a MAIS
        LONGA é a principal e as demais, preparatórias. Só sugere pra prova futura
        e com distância conhecida — sem pista, não chuta."""

        future = [r for r in races if r.get("date") and r["date"] >= today]

        if len(future) == 1:

            return {future[0]["id"]: "A"}

        known = [r for r in future if r.get("distance_km")]

        if not known:

            return {}

        # o atleta já escolheu a principal: as outras sem escolha são
        # preparatórias — a sugestão nunca cria uma 2ª principal
        if any(r.get("priority") == "A" for r in future):

            return {r["id"]: "B" for r in known}

        # empate de distância: a mais tarde (o objetivo costuma vir por último)
        main = max(known, key=lambda r: (r["distance_km"], r["date"]))

        return {
            r["id"]: ("A" if r is main else "B") for r in known
        }

    @staticmethod
    def add(
        profile: str,
        name: str,
        date: str,
        target_time: str | None = None,
        distance_km: float | None = None,
        priority: str | None = None,
    ) -> dict:

        repo = RaceRepository()

        record = repo.add(
            profile, name, date, target_time,
            distance_km=distance_km, priority=priority,
        )

        # o coach passa a saber da prova (equilibra no plano)
        desc = f"Prova cadastrada pelo app: {name} em {date}"

        if target_time:

            desc += f" (alvo {target_time})"

        if priority in PRIORITIES:

            desc += f" — prova {PRIORITY_LABELS[priority]} ({priority})"

        try:

            RunnerMemoryService.process(
                profile, {"add": [{"category": "objetivo", "content": desc}]}
            )

        except Exception as e:

            print(f"Falha ao registrar prova na memória de '{profile}': {e}")

        RaceService._sync_anchor(profile, repo)

        return record

    @staticmethod
    def record_from_conversation(
        profile: str,
        name: str | None,
        date: str | None,
        target_time: str | None = None,
        distance_km: float | None = None,
        priority: str | None = None,
    ) -> dict | None:
        """Registra na LISTA estruturada uma prova que veio da CONVERSA (cérebro
        do coach, fluxo antigo de meta) ou do cadastro: nome, data, distância,
        tempo-alvo e — quando o atleta deixou claro — o papel (A/B/C). Sem efeito
        colateral no perfil nem na memória (quem chama já cuida da âncora e do
        que o coach lembra): só a lista, que é o calendário que o coach lê.

        Só provas FUTURAS entram (a passada é histórico, não calendário). Dedup
        por data + nome; completa distância/tempo/papel que faltavam. Um papel A
        novo rebaixa a outra principal ESCOLHIDA pro papel B. Best-effort: devolve
        None sem data/sem nome utilizável, nunca levanta."""

        try:

            if not date or date < today_local().isoformat():

                return None

            label = (name or "").strip() or (
                f"{distance_km:g} km" if distance_km else "Prova"
            )

            repo = RaceRepository()

            record = repo.upsert(profile, label, date, target_time)

            fields: dict = {}

            # a distância dita na conversa manda (o nome só dá a aproximada:
            # "(21 km)" é a meia de 21,0975)
            if distance_km and record.get("distance_km") != distance_km:

                fields["distance_km"] = distance_km

            if priority in PRIORITIES and record.get("priority") != priority:

                fields["priority"] = priority

            if fields:

                record = repo.update(profile, record["id"], fields) or record

            if priority == "A":

                RaceService._demote_other_principals(profile, repo, record["id"])

            return record

        except Exception as e:

            print(f"Prova da conversa não entrou na lista de '{profile}': {e}")

            return None

    @staticmethod
    def _demote_other_principals(
        profile: str, repo: RaceRepository, keep_id: str
    ) -> None:
        """Uma nova principal (A) escolhida: a outra A escolhida (prova futura)
        vira preparatória (B). O atleta reverte na tela de provas."""

        today = today_local().isoformat()

        for race in repo.load(profile):

            if (
                race.get("id") != keep_id
                and race.get("priority") == "A"
                and (race.get("date") or "") >= today
            ):

                repo.update(profile, race["id"], {"priority": "B"})

    @staticmethod
    def update(
        profile: str,
        race_id: str,
        priority: str | None = None,
        distance_km: float | None = None,
    ) -> dict | None:
        """Muda o papel (A/B/C) e/ou a distância de uma prova. Não mexe na
        âncora (essa depende da data). None se a prova não existe; ValueError
        pra papel inválido."""

        fields: dict = {}

        if priority is not None:

            if priority not in PRIORITIES:

                raise ValueError("Papel inválido (use A, B ou C).")

            fields["priority"] = priority

        if distance_km is not None:

            fields["distance_km"] = distance_km

        if not fields:

            return None

        return RaceRepository().update(profile, race_id, fields)

    @staticmethod
    def remove(profile: str, race_id: str) -> bool:

        repo = RaceRepository()

        removed = repo.remove(profile, race_id)

        if removed:

            RaceService._sync_anchor(profile, repo)

        return removed

    # ---- âncora do perfil ----

    @staticmethod
    def _sync_anchor(profile: str, repo: RaceRepository) -> None:
        """Recomputa a prova-âncora do perfil a partir da lista. Só mexe no
        perfil quando o app está gerenciando provas (lista não-vazia): se há
        prova futura, ela ancora; se todas já passaram, limpa a âncora (volta ao
        treino de base). Nunca toca no perfil de quem nunca usou o recurso."""

        races = repo.load(profile)

        if not races:

            return

        today = today_local().isoformat()

        future = sorted(
            (r for r in races if r.get("date") and r["date"] >= today),
            key=lambda r: r["date"],
        )

        prof = RunnerProfileRepository()

        if future:

            nearest = future[0]

            prof.update_fields(
                profile,
                {
                    "target_race": nearest.get("name"),
                    "race_date": nearest.get("date"),
                    "target_time": nearest.get("target_time"),
                },
            )

        else:

            prof.update_fields(
                profile,
                {"target_race": None, "race_date": None, "target_time": None},
            )

    @staticmethod
    def _import_profile_anchor(
        profile: str, repo: RaceRepository, races: list[dict]
    ) -> None:
        """Se o coach setou uma prova por conversa (perfil tem race_date +
        target_race) e ela não está na lista, importa — pra a lista do app não
        perder a prova que já existia."""

        try:

            runner = RunnerProfileRepository().load(profile)

        except Exception:

            return

        date = getattr(runner, "race_date", None)
        name = getattr(runner, "target_race", None)

        if not (date and name):

            return

        # mesma data = mesmo evento (o nome muda de boca em boca)
        already = any(r.get("date") == date for r in races)

        if not already:

            repo.add(profile, name, date, getattr(runner, "target_time", None))
