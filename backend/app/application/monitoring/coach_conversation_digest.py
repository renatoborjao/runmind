"""O QUE O COACH DISSE NA SEMANA — SEM IA, só leitura. Junta, por atleta e em ordem de tempo, tudo
que o coach falou e o que o atleta disse numa janela (padrão: 7 dias), pra um revisor (o agente
`revisor-de-conversas` ou o próprio dono) julgar a QUALIDADE do coach com olho de treinador:

  chat          as falas do atleta e as respostas do coach
  proativo      o que o coach mandou sozinho (briefing, alerta, lembrete) — se não repetiu no chat;
                inclui o que já saiu da janela do outbox (guarda só os 10 últimos) e foi pro arquivo
  análise       a análise de cada treino gravada na janela
  cérebro       mensagens do atleta em que o roteador caiu no plano B (fallback) ou que chegaram com
                uma proposta do coach EM ABERTO (o atleta respondeu com uma oferta pendente)
  memória       o que foi gravado na memória do atleta (pra ver se algo dito se perdeu)
  plano         o plano gravado da semana, sessão por sessão (pra conferir promessa × plano)
  proposta      a proposta de mudança de plano que ainda espera o "sim" do atleta, se houver

Não muda nada e não manda nada: só imprime. Dado de atleta fica na VM — rodar lá e ler na tela
(`bash ops/relatorio_vm.sh conversas [dias]`). As peças puras (`collect`, `render`) recebem
listas e são testadas offline; `CoachConversationDigest` só as liga aos repositórios.

    python -m app.application.monitoring.coach_conversation_digest              # 7 dias, todos
    python -m app.application.monitoring.coach_conversation_digest --dias 3
    python -m app.application.monitoring.coach_conversation_digest --atleta fernanda"""

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

DEFAULT_DAYS = 7

DEFAULT_TZ = "America/Sao_Paulo"

# um texto muito longo é cortado (com aviso) pra a leitura caber; o revisor vê o começo, que é o
# que o atleta lê primeiro
MAX_ITEM_CHARS = 2500

_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


@dataclass(frozen=True)
class Item:

    when: datetime

    kind: str

    text: str


def parse_ts(value) -> datetime | None:
    """ISO → datetime com fuso. Sem fuso = UTC (é como o servidor grava). Lixo → None."""

    if not value or not isinstance(value, str):

        return None

    try:

        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))

    except ValueError:

        return None

    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _norm(text: str) -> str:

    return " ".join((text or "").split())


def collect(
    since: datetime,
    chat: list[dict] | None = None,
    outbox: list[dict] | None = None,
    analyses: dict | None = None,
    brain_log: list[dict] | None = None,
    memories: list | None = None,
) -> list[Item]:
    """Tudo da janela (a partir de `since`), em ordem de tempo. Entradas sem data válida ficam de
    fora; o proativo que já aparece igual no chat não é repetido."""

    items: list[Item] = []

    said: set[str] = set()

    for turn in chat or []:

        when = parse_ts(turn.get("timestamp"))

        if when is None or when < since:

            continue

        who = "atleta" if turn.get("role") == "user" else "coach"

        if who == "coach":

            said.add(_norm(turn.get("text", "")))

        items.append(Item(when, who, turn.get("text", "")))

    for entry in outbox or []:

        when = parse_ts(entry.get("timestamp"))

        if when is None or when < since or _norm(entry.get("text", "")) in said:

            continue

        items.append(Item(when, "coach (proativo)", entry.get("text", "")))

    for analysis in (analyses or {}).values():

        if not isinstance(analysis, dict):

            continue

        when = parse_ts(analysis.get("created_at"))

        if when is None or when < since:

            continue

        km = analysis.get("distance_km")

        head = " · ".join(
            str(x)
            for x in (
                analysis.get("date"),
                analysis.get("workout_type"),
                f"{km:.1f} km" if isinstance(km, (int, float)) else None,
            )
            if x
        )

        items.append(Item(when, f"análise do treino ({head})", analysis.get("analysis", "")))

    for entry in brain_log or []:

        if not (entry.get("fallback") or entry.get("pending")):

            continue

        when = parse_ts(entry.get("ts"))

        if when is None or when < since:

            continue

        flag = (
            "plano B (fallback)" if entry.get("fallback")
            else "chegou com proposta do coach em aberto"
        )

        items.append(
            Item(
                when,
                f"cérebro: {flag}",
                f"entrada: {entry.get('incoming', '')}\ndisse: {entry.get('say', '')}",
            )
        )

    for memory in memories or []:

        get = memory.get if isinstance(memory, dict) else lambda k, m=memory: getattr(m, k, None)

        when = parse_ts(get("created_at"))

        if when is None or when < since:

            continue

        items.append(
            Item(
                when,
                f"memória gravada ({get('category')}, {get('status')})",
                get("content") or "",
            )
        )

    items.sort(key=lambda i: i.when)

    return items


def _stamp(when: datetime, tz: ZoneInfo) -> str:

    local = when.astimezone(tz)

    return f"{_WEEKDAYS[local.weekday()]} {local:%d/%m %H:%M}"


def _cut(text: str) -> str:

    text = (text or "").strip()

    if len(text) <= MAX_ITEM_CHARS:

        return text

    return text[:MAX_ITEM_CHARS].rstrip() + f" […cortado: {len(text)} caracteres no total]"


def proposal_lines(proposal) -> list[str]:
    """A proposta pendente em poucas linhas: tipo, semana e cada mudança (dia → o que entra)."""

    if proposal is None:

        return []

    get = proposal.get if isinstance(proposal, dict) else lambda k: getattr(proposal, k, None)

    lines = [f"tipo {get('kind')} · semana {get('week_start')}"]

    for op in get("operations") or []:

        session = op.get("session") or {}

        what = " · ".join(
            str(x)
            for x in (
                session.get("workout_type"),
                f"{session.get('planned_distance_km')} km" if session.get("planned_distance_km") else None,
                f"{session.get('planned_duration_minutes')} min"
                if session.get("planned_duration_minutes") else None,
            )
            if x
        )

        lines.append(f"{op.get('action')} {op.get('day')}" + (f": {what}" if what else ""))

    return lines


def render(
    name: str,
    items: list[Item],
    plan_lines: list[str],
    tz: ZoneInfo,
    days: int,
    pending: list[str] | None = None,
) -> str:
    """O bloco de UM atleta, pronto pra ler na tela."""

    chat = sum(1 for i in items if i.kind == "atleta")

    out = [
        f"===== {name} — últimos {days} dias "
        f"({chat} mensagem(ns) do atleta, {len(items)} registro(s)) =====",
        "",
        "-- plano gravado --",
    ]

    out.extend(plan_lines or ["(sem plano gravado)"])

    out.append("")

    out.append("-- proposta em aberto (espera o sim do atleta) --")

    out.extend(pending or ["(nenhuma)"])

    out.append("")

    if not items:

        out.append("(nada na janela)")

    for item in items:

        out.append(f"[{_stamp(item.when, tz)}] {item.kind}:")

        out.append(_cut(item.text))

        out.append("")

    return "\n".join(out).rstrip() + "\n"


# --- ligação com os dados reais -------------------------------------------------------------------


class CoachConversationDigest:

    @staticmethod
    def athletes() -> list[str]:

        from app.infrastructure.persistence.runner_profile_repository import (
            RunnerProfileRepository,
        )

        return RunnerProfileRepository().list_active()

    @staticmethod
    def for_profile(profile: str, days: int, now: datetime) -> str:

        from app.application.coach.writer.coach_persona import first_name
        from app.application.monitoring.plan_generation_monitor import (
            _RUN_KINDS,
            session_line,
        )
        from app.application.use_cases.load_runner_profile import LoadRunnerProfile
        from app.core.clock import use_athlete_timezone
        from app.infrastructure.persistence.coach_brain_log_repository import (
            CoachBrainLogRepository,
        )
        from app.infrastructure.persistence.coach_outbox_repository import (
            CoachOutboxRepository,
        )
        from app.infrastructure.persistence.permanent_archive import PermanentArchive
        from app.infrastructure.persistence.plan_proposal_repository import (
            PlanProposalRepository,
        )
        from app.infrastructure.persistence.conversation_repository import (
            ConversationRepository,
        )
        from app.infrastructure.persistence.runner_memory_repository import (
            RunnerMemoryRepository,
        )
        from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository
        from app.infrastructure.persistence.workout_analysis_repository import (
            WorkoutAnalysisRepository,
        )

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        tz = ZoneInfo(runner.timezone or DEFAULT_TZ)

        since = now - timedelta(days=days)

        outbox_repo = CoachOutboxRepository()

        archived = [
            row.get("record")
            for row in PermanentArchive.load(outbox_repo.storage, "coach_outbox", profile)
            if isinstance(row.get("record"), dict)
        ]

        try:

            proposal = PlanProposalRepository().load(profile)

        except Exception:  # noqa: BLE001 — proposta ilegível não derruba o resumo

            proposal = None

        items = collect(
            since,
            chat=ConversationRepository().load(profile),
            outbox=archived + outbox_repo._load(profile),
            analyses=WorkoutAnalysisRepository()._load(profile),
            brain_log=CoachBrainLogRepository().load(profile),
            memories=RunnerMemoryRepository().load(profile),
        )

        plan = WeeklyPlanRepository().load(profile)

        plan_lines = []

        if plan is not None:

            sessions = [s for s in plan.sessions if getattr(s, "kind", "run") in _RUN_KINDS]

            plan_lines = [session_line(s) for s in sessions]

        return render(
            first_name(runner.name) or profile, items, plan_lines, tz, days,
            pending=proposal_lines(proposal),
        )


def run(days: int = DEFAULT_DAYS, only: str | None = None, now: datetime | None = None) -> str:

    now = now or datetime.now(UTC)

    blocks = []

    for profile in CoachConversationDigest.athletes():

        if only and profile != only:

            continue

        try:

            blocks.append(CoachConversationDigest.for_profile(profile, days, now))

        except Exception as e:  # noqa: BLE001 — um atleta torto não derruba os outros

            blocks.append(f"===== {profile} — não consegui ler: {e} =====\n")

    text = "\n".join(blocks) if blocks else "(nenhum atleta ativo)\n"

    print(text)

    return text


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])

    parser.add_argument("--dias", type=int, default=DEFAULT_DAYS)

    parser.add_argument("--atleta", default=None)

    args = parser.parse_args()

    run(days=max(1, args.dias), only=args.atleta)
