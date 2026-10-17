"""Provas do atleta pelo app: cadastrar uma ou VÁRIAS, listar e remover — sem
quebrar a periodização, que continua ancorada na prova datada MAIS PRÓXIMA pelos
campos do perfil (target_race/race_date/target_time).

O RaceService é a cola: a lista estruturada mora no [[RaceRepository]]; a cada
mudança ele recomputa a âncora do perfil (a prova futura mais próxima) e, ao
adicionar, registra na memória evolutiva (o coach passa a equilibrar a prova no
plano — [[project_multiplos_objetivos]]). Na leitura, reconcilia a prova que o
coach setou por conversa (importa pra lista), pra os dois lados baterem."""

from __future__ import annotations

import re

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

    # ---- cancelamento e remarcação vindos da conversa ----

    @staticmethod
    def cancel_from_conversation(
        profile: str,
        name: str | None = None,
        date: str | None = None,
    ) -> dict | None:
        """O atleta disse que uma prova FOI CANCELADA: tira da lista a prova
        certa. Quem é a certa: a data dita (exata, ou o único mês batendo), senão
        o nome/distância dita (só se bater com UMA prova), senão — se nada foi
        identificado — a âncora do plano. Disse qual e não achou, ou ficou
        ambíguo: não remove nada (melhor que tirar a prova errada). Só provas
        futuras (a que já passou é histórico). Devolve a removida ou None;
        nunca levanta."""

        try:

            repo = RaceRepository()

            future = RaceService._future(repo.load(profile))

            if not future:

                return None

            target = RaceService._resolve(profile, future, name, date)

            if target is None:

                return None

            repo.remove(profile, target["id"])

            return target

        except Exception as e:

            print(f"Cancelar prova de '{profile}' falhou: {e}")

            return None

    @staticmethod
    def reschedule_from_conversation(
        profile: str,
        name: str | None,
        new_date: str | None,
        target_time: str | None = None,
        moved_from: str | None = None,
    ) -> dict | None:
        """A prova ADIOU/MUDOU DE DATA: muda a data da MESMA prova na lista em
        vez de criar outra (e deixar a antiga como fantasma). A mesma prova é a da
        data antiga dita (`moved_from`) ou, sem ela, a ÚNICA futura com nome
        equivalente (e distância compatível). Já existe prova na data nova, ou
        ficou ambíguo: None — quem chama registra como prova nova. Nunca levanta."""

        try:

            if not new_date or new_date < today_local().isoformat():

                return None

            repo = RaceRepository()

            races = repo.load(profile)

            if any(r.get("date") == new_date for r in races):

                return None

            future = RaceService._future(races)

            if moved_from:

                matches = [r for r in future if r.get("date") == moved_from]

            else:

                # sem a data antiga, só o NOME equivalente vale (distância sozinha
                # juntaria duas provas diferentes de 15 km)
                matches = [
                    r for r in future
                    if RaceService._same_race_name(name, r, by_distance=False)
                ]

            if len(matches) != 1:

                return None

            fields = {"date": new_date}

            if target_time:

                fields["target_time"] = target_time

            return repo.update(profile, matches[0]["id"], fields)

        except Exception as e:

            print(f"Remarcar prova de '{profile}' falhou: {e}")

            return None

    @staticmethod
    def resync_anchor(profile: str) -> bool:
        """Recalcula a âncora do perfil (a prova futura mais próxima) depois de
        a lista mudar. True se ainda há prova à frente (âncora redefinida);
        False se não sobrou nenhuma (o chamador limpa a âncora)."""

        repo = RaceRepository()

        if not RaceService._future(repo.load(profile)):

            return False

        RaceService._sync_anchor(profile, repo)

        return True

    @staticmethod
    def _future(races: list[dict]) -> list[dict]:

        today = today_local().isoformat()

        return [r for r in races if (r.get("date") or "") >= today]

    @staticmethod
    def _resolve(
        profile: str,
        future: list[dict],
        name: str | None,
        date: str | None,
    ) -> dict | None:
        """Qual prova futura o atleta quis dizer. Data > nome > âncora. Quando
        ele identificou a prova e nada bate (ou bate mais de uma), None."""

        if date:

            exact = [r for r in future if r.get("date") == date]

            if len(exact) == 1:

                return exact[0]

            # "a de dezembro": sem dia exato o dia 15 do mês — vale o único mês
            same_month = [
                r for r in future if (r.get("date") or "")[:7] == date[:7]
            ]

            return same_month[0] if len(same_month) == 1 else None

        if name:

            matches = [r for r in future if RaceService._same_race_name(name, r)]

            return matches[0] if len(matches) == 1 else None

        # nada identificado: a âncora do plano
        try:

            anchor_date = str(
                getattr(RunnerProfileRepository().load(profile), "race_date", "")
                or ""
            )[:10]

        except Exception:

            return None

        anchored = [r for r in future if r.get("date") == anchor_date]

        return anchored[0] if len(anchored) == 1 else None

    @staticmethod
    def _name_core(name: str | None) -> str:
        """O nome PRÓPRIO da prova, sem distância nem palavras genéricas:
        'Santander … Villa-Lobos (15 km)' -> '... villa-lobos'; '15 km' -> ''."""

        text = re.sub(
            r"\d+(?:[.,]\d+)?\s*(?:km|k|quil[oô]metros?)\b", " ", (name or "").lower()
        )

        words = [
            w.strip("()[]—-–,.:;")
            for w in text.split()
        ]

        generic = {
            "de", "da", "do", "das", "dos", "a", "o", "e", "em", "meia",
            "maratona", "prova", "corrida", "km", "k", "",
        }

        return " ".join(w for w in words if w not in generic and not w.isdigit())

    @staticmethod
    def _same_race_name(
        name: str | None, race: dict, by_distance: bool = True
    ) -> bool:
        """O nome dito é desta prova? Nome equivalente (um contém o outro) ou,
        com `by_distance`, a distância dita ("a meia", "a 15k") bate com a dela
        (quem chama exige que seja a ÚNICA que bate)."""

        said = RaceService._name_core(name)

        listed = RaceService._name_core(race.get("name"))

        # só o NOME PRÓPRIO conta ("Villa-Lobos"); "15 km" / "meia maratona" não
        # têm nome próprio — esses caem na distância
        if len(said) >= 4 and len(listed) >= 4 and (said in listed or listed in said):

            return True

        if not by_distance:

            return False

        said_km = parse_race_distance(name)

        listed_km = race.get("distance_km") or parse_race_distance(race.get("name"))

        return bool(
            said_km and listed_km and abs(said_km - listed_km) < 0.5
        )

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
