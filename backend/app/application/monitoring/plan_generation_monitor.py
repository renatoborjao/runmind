"""CONFERÊNCIA DA GERAÇÃO DO PLANO DE DOMINGO — SEM IA, só leitura. No domingo, às 20h do fuso de
cada atleta, o coach gera e entrega o plano da semana. Este monitor confere DEPOIS o que saiu —
o que o dono só via entrando no servidor ou quando o atleta reclamava:

  entrega        o plano da semana existe e a mensagem saiu (e a que horas)
  plano de rede  a IA falhou e o atleta recebeu o plano genérico (nenhuma sessão com a estrutura
                 escrita pelo coach)
  corte          quem ENTREGOU a semana passada recebeu um plano menor (ou marcado como descarga)
  maior treino   o maior treino do plano passa 10% do maior das últimas 4 semanas
  repetição      treino forte igual ao da semana passada (mesmo tipo e mesma série)
  custo          o que a geração gastou de IA, por atleta e no total
  falha          marcadores de erro no journal do serviço desde domingo

É só um aviso: não muda NADA. Os checks são puros (recebem números) e testados offline;
`PlanGenerationMonitor` só os liga aos dados reais. O volume contra a rota e os saltos de
semana são da revisão diária (`coach_sanity_audit`, segunda 08:30) — aqui só o que é da geração.

    python -m app.application.monitoring.plan_generation_monitor           # mostra (dry-run)
    python -m app.application.monitoring.plan_generation_monitor --texto   # + o texto recebido
    python -m app.application.monitoring.plan_generation_monitor --send    # avisa o dono (cron)

Cron (VM, em UTC): `30 0 * * 1` = domingo 21:30 em Brasília, ~90 min depois da geração das 20h."""

import argparse
import asyncio
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.application.history import stimulus_ledger
from app.application.monitoring.coach_sanity_audit import (
    HIGH,
    WATCH,
    Finding,
    _send,
)

# --- limiares (todos em um lugar; o aviso é pra OLHAR, não pra decidir) ---------------------------

# a hora local da entrega (a mesma de `WeeklyPlanNotifier.PLAN_HOUR`) e a hora local de domingo a
# partir da qual o monitor confere o atleta (a geração leva ~1 min; sobra folga pro envio)
DELIVERY_HOUR = 20
CHECK_HOUR = 21

# a mensagem saiu mais de tantos minutos depois da hora da entrega
LATE_MINUTES = 90

# quem ENTREGOU a semana passada e recebeu um plano mais de tanto abaixo do que fez
CUT_TOLERANCE = 0.10

# o maior treino do plano passa tanto do maior das últimas semanas fechadas: um salto numa sessão só
# é o melhor previsor de lesão (Frandsen et al., BJSM 2025), melhor que a rampa semanal
LONG_SPIKE_MAX = 0.10
RECENT_WEEKS = 4

# custo da IA: por plano (o normal é ~R$ 0,30; um bloco novo soma ~R$ 0,70) e no total desde domingo
PLAN_COST_WARN_BRL = 1.50
TOTAL_COST_WARN_BRL = 5.00

# a mensagem do plano só é achada no registro de envios (guarda as últimas 10) por poucos dias
FRESH_DAYS = 3

DEFAULT_TZ = "America/Sao_Paulo"

# preços de lista (USD por 1M de tokens): (entrada, saída) — os mesmos de ops/plan_audit.py
USD_BRL = 5.40

PRICING = {
    "gemini-3.6-flash": (0.15, 0.60),
    "gemini-3.5-flash-lite": (0.075, 0.30),
    "gemini-3.1-pro-preview": (1.25, 10.00),
    "_default": (0.15, 0.60),
}

# os rótulos de chamada de IA que montam o plano da semana
PLAN_LABELS = ("plan", "auto:coach_plan_engine")

# famílias de estímulo que contam como treino FORTE
_QUALITY = {
    stimulus_ledger.RACE_PACE,
    stimulus_ledger.HILLS,
    stimulus_ledger.FARTLEK,
    stimulus_ledger.THRESHOLD,
    stimulus_ledger.VO2,
    stimulus_ledger.PROGRESSION,
}

_RUN_KINDS = ("run", "walk", "run_walk")

# marcador no journal → (código, o que aconteceu). Os textos vêm dos `print` do próprio app
JOURNAL_MARKS = (
    ("IA falhou no plano de", "ia_falhou", "A IA falhou ao gerar o plano e caiu no plano de rede."),
    ("Falha ao enviar plano semanal para", "envio_falhou", "O envio do plano semanal falhou."),
    (
        "weekly_plan suprimido p/",
        "envio_suprimido",
        "O governador de mensagens segurou o plano semanal: ele não saiu.",
    ),
)

TITLES = {
    "sem_plano": "Plano da semana não foi gerado",
    "plano_nao_enviado": "Plano gerado, mas a mensagem não saiu",
    "entrega_atrasada": "Plano entregue com atraso",
    "plano_de_rede": "Plano genérico no lugar do plano do coach",
    "corte_apos_entrega": "Cortou o volume de quem entregou",
    "salto_do_maior_treino": "Maior treino da semana salta sobre o recente",
    "treino_forte_repetido": "Treino forte igual ao da semana passada",
    "custo_alto": "Geração mais cara que o normal",
    "ia_falhou": "A IA falhou na geração",
    "envio_falhou": "Falha no envio do plano",
    "envio_suprimido": "Mensagem do plano segurada pelo governador",
    "sem_conferencia": "Não consegui conferir",
}

ACTIONS = {
    "sem_plano": (
        "O atleta está sem plano. Peça pro Claude gerar a semana dele (1 chamada de IA, ~R$ 0,40)."
    ),
    "plano_nao_enviado": "Confira o envio (Telegram e app) e reenvie a mensagem.",
    "entrega_atrasada": "Veja no journal do serviço o que atrasou o envio das 20h.",
    "plano_de_rede": (
        "Ele recebeu um plano sem a cara do coach. Peça pro Claude refazer a semana dele "
        "(1 chamada de IA, ~R$ 0,40)."
    ),
    "corte_apos_entrega": (
        "Quem entrega absorve a carga: o coach deveria segurar o volume. Se o corte não tem uma "
        "causa clara, refaça a semana."
    ),
    "salto_do_maior_treino": (
        "Subir o maior treino de uma vez é o que mais machuca. Vale limitar a ~10% sobre o maior "
        "recente."
    ),
    "treino_forte_repetido": "Se não é de propósito, o coach precisa variar a série ou o ritmo.",
    "custo_alto": "Veja de onde veio o gasto: bash ops/plan_audit.sh --day <dia>.",
    "ia_falhou": "Confira o plano que ele recebeu e, se for genérico, refaça a semana.",
    "envio_falhou": "Confira se a mensagem chegou ao atleta.",
    "envio_suprimido": "O plano só chega se alguém liberar: veja o teto diário do governador.",
    "sem_conferencia": "O monitor não conseguiu ler os dados dele: veja o log do cron.",
}


@dataclass(slots=True)
class Facts:
    """Os números de UM atleta na conferência do domingo (tudo já lido: os checks são puros)."""

    profile: str
    name: str
    sunday: date
    week: date
    since: datetime
    due: bool = False
    fresh: bool = True
    external: bool = False
    plan_week: date | None = None
    new_km: float = 0.0
    sessions: int = 0
    structured: int = 0
    longest_plan_km: float = 0.0
    is_deload: bool = False
    deload_why: str = ""
    sent: list[datetime] = field(default_factory=list)
    delivering: bool = False
    last_planned_km: float = 0.0
    last_done_km: float = 0.0
    longest_recent_km: float = 0.0
    repeated: list[str] = field(default_factory=list)
    plan_cost_brl: float = 0.0
    text: str = ""


# --- apoio puro ----------------------------------------------------------------------------------


def last_sunday(now: datetime) -> datetime:
    """O domingo mais recente (hoje, se for domingo) às 00:00 no fuso de `now`."""

    back = (now.weekday() + 1) % 7

    return (now - timedelta(days=back)).replace(hour=0, minute=0, second=0, microsecond=0)


def cost_brl(record: dict) -> float:
    """Custo-sombra de UMA chamada de IA (preço de lista; é o que o medidor registra)."""

    pin, pout = PRICING.get(record.get("model"), PRICING["_default"])

    tokens_in = record.get("in") or 0

    tokens_out = (record.get("out") or 0) + (record.get("thoughts") or 0)

    return (tokens_in * pin + tokens_out * pout) / 1_000_000 * USD_BRL


def _parse_ts(value) -> datetime | None:

    try:

        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    except ValueError:

        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _km(value: float) -> str:

    text = f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"

    return f"{text.replace('.', ',')} km"


def _money(value: float) -> str:

    return f"R$ {value:.2f}".replace(".", ",")


def _short(text: str, limit: int = 140) -> str:

    clean = " ".join((text or "").split())

    return clean if len(clean) <= limit else clean[:limit].rsplit(" ", 1)[0] + "…"


def _steps_key(steps) -> tuple:

    return tuple(
        (
            step.kind,
            step.reps,
            round(step.distance_m or 0),
            step.duration_sec,
            step.pace_min,
            step.pace_max,
            _steps_key(step.steps),
        )
        for step in steps or []
    )


def _signature(session) -> tuple | None:
    """A identidade do treino pra comparar semana a semana: os passos estruturados (séries,
    distâncias, ritmos); sem passos, o texto da estrutura. None quando não há o que comparar."""

    steps = _steps_key(getattr(session, "steps", None))

    if steps:

        return ("steps", steps)

    text = " ".join((getattr(session, "structure", "") or "").lower().split())

    return ("text", text) if text else None


def repeated_sessions(new_sessions: list, previous_sessions: list) -> list[str]:
    """Os treinos FORTES do plano novo que repetem, iguais (mesma família e mesma série), um da
    semana passada. Rodagem e longão repetidos não contam: o que cansa é o treino forte igual."""

    classify = stimulus_ledger.StimulusLedger.classify

    before = {
        (classify(s.workout_type), _signature(s))
        for s in previous_sessions
        if getattr(s, "kind", "run") in _RUN_KINDS and _signature(s) is not None
    }

    out = []

    for session in new_sessions:

        family = classify(session.workout_type)

        signature = _signature(session)

        if family not in _QUALITY or signature is None or (family, signature) not in before:

            continue

        km = session.effective_distance_km

        out.append(f"{session.workout_type} ({_km(km)})" if km else session.workout_type)

    return out


# --- os checks (puros) ---------------------------------------------------------------------------


def delivery(f: Facts) -> list[Finding]:
    """A entrega: o plano da semana existe e a mensagem saiu perto da hora marcada."""

    if f.external or not f.due:

        return []

    if f.plan_week != f.week:

        had = (
            "nenhum plano guardado"
            if f.plan_week is None
            else f"o plano guardado é da semana de {f.plan_week:%d/%m}"
        )

        return [
            Finding(
                f.profile, "sem_plano", HIGH,
                f"Era pra existir o plano da semana de {f.week:%d/%m} (entrega de domingo às "
                f"{DELIVERY_HOUR}h) e há {had}.",
            )
        ]

    if not f.fresh:

        return []

    if not f.sent:

        return [
            Finding(
                f.profile, "plano_nao_enviado", HIGH,
                f"O plano da semana de {f.week:%d/%m} está gerado ({_km(f.new_km)}), mas não há "
                "mensagem de plano enviada desde domingo no registro de envios.",
            )
        ]

    due = datetime.combine(f.sunday, time(DELIVERY_HOUR), tzinfo=f.sent[0].tzinfo)

    late = (f.sent[0] - due).total_seconds() / 60

    if late > LATE_MINUTES:

        return [
            Finding(
                f.profile, "entrega_atrasada", WATCH,
                f"A mensagem do plano saiu às {f.sent[0]:%H:%M}, {late:.0f} min depois das "
                f"{DELIVERY_HOUR}h.",
            )
        ]

    return []


def network_plan(f: Facts) -> Finding | None:
    """O plano veio do plano de rede? As sessões do coach trazem a estrutura escrita (aquecimento,
    série, foco); o plano genérico não — sem nenhuma estrutura, a IA falhou."""

    if f.external or f.plan_week != f.week or f.sessions == 0:

        return None

    if f.structured == 0:

        return Finding(
            f.profile, "plano_de_rede", HIGH,
            f"Nenhuma das {f.sessions} sessões tem a estrutura escrita pelo coach: a IA falhou e o "
            "plano que saiu foi o genérico (de rede).",
        )

    if f.structured < f.sessions:

        return Finding(
            f.profile, "plano_de_rede", WATCH,
            f"Só {f.structured} de {f.sessions} sessões têm a estrutura escrita pelo coach.",
        )

    return None


def cut_after_delivery(f: Facts) -> Finding | None:
    """Quem ENTREGOU a semana passada não deve receber um plano menor: entregar é absorver. Alerta
    forte quando o volume cai mais de `CUT_TOLERANCE` sobre o que fez; atenção quando só a semana
    vem marcada como descarga."""

    if f.external or f.plan_week != f.week or not f.delivering:

        return None

    if f.last_done_km <= 0 or f.new_km <= 0:

        return None

    # a base é o MENOR entre o que foi pedido e o que ele fez: quem passou do plano (Mauricio, 42 km
    # num plano de 37) e recebe a prescrição de volta (38 km) não foi cortado
    base = min(f.last_done_km, f.last_planned_km) if f.last_planned_km > 0 else f.last_done_km

    change = f.new_km / base - 1

    cut = change < -CUT_TOLERANCE

    if not cut and not f.is_deload:

        return None

    head = (
        f"Entregou a semana passada ({_km(f.last_done_km)} feitos de {_km(f.last_planned_km)} "
        f"planejados) e o plano novo pede {_km(f.new_km)} ({change:+.0%} sobre {_km(base)})."
    )

    if f.is_deload and f.deload_why:

        why = f' O coach declarou descarga: "{_short(f.deload_why)}".'

    elif f.is_deload:

        why = " O coach marcou a semana como descarga."

    else:

        why = " Sem descarga declarada."

    return Finding(f.profile, "corte_apos_entrega", HIGH if cut else WATCH, head + why)


def long_jump(f: Facts) -> Finding | None:
    """O maior treino do plano contra o maior das últimas semanas fechadas."""

    if f.external or f.plan_week != f.week:

        return None

    if f.longest_recent_km <= 0 or f.longest_plan_km <= 0:

        return None

    over = f.longest_plan_km / f.longest_recent_km - 1

    if over <= LONG_SPIKE_MAX:

        return None

    return Finding(
        f.profile, "salto_do_maior_treino", WATCH,
        f"O maior treino do plano ({_km(f.longest_plan_km)}) passa {over:.0%} do maior das últimas "
        f"{RECENT_WEEKS} semanas ({_km(f.longest_recent_km)}).",
    )


def repeated_quality(f: Facts) -> Finding | None:

    if f.external or not f.repeated:

        return None

    return Finding(
        f.profile, "treino_forte_repetido", WATCH,
        "Treino forte igual ao da semana passada (mesmo tipo e mesma série): "
        + "; ".join(f.repeated) + ".",
    )


def checks(f: Facts) -> list[Finding]:
    """Todos os checks de UM atleta."""

    found = list(delivery(f))

    for check in (network_plan, cut_after_delivery, long_jump, repeated_quality):

        item = check(f)

        if item is not None:

            found.append(item)

    return found


def cost_findings(per_plan: dict[str, float], total: float) -> list[Finding]:
    """O gasto de IA da geração: por atleta (planos) e no total desde domingo."""

    out = [
        Finding(
            profile, "custo_alto", WATCH,
            f"A geração do plano custou {_money(value)} de IA (o normal é ~R$ 0,30 por plano, mais "
            "~R$ 0,70 quando abre um bloco novo).",
        )
        for profile, value in sorted(per_plan.items())
        if value > PLAN_COST_WARN_BRL
    ]

    if total > TOTAL_COST_WARN_BRL:

        out.append(
            Finding(
                "geral", "custo_alto", WATCH,
                f"A IA gastou {_money(total)} desde domingo (o normal fica em ~R$ 2,50).",
            )
        )

    return out


def journal_findings(lines: list[str]) -> list[Finding]:
    """Os marcadores de falha da geração no journal do serviço, um achado por (atleta, tipo)."""

    out: list[Finding] = []

    seen: set[tuple[str, str]] = set()

    for line in lines:

        for mark, code, text in JOURNAL_MARKS:

            if mark not in line:

                continue

            found = re.search(r"'([^']+)'", line[line.index(mark):])

            profile = found.group(1) if found else "geral"

            if (profile, code) not in seen:

                seen.add((profile, code))

                out.append(Finding(profile, code, HIGH, text))

    return out


def read_journal(since: datetime) -> list[str] | None:
    """As linhas do journal do serviço desde `since`. None quando não dá pra ler (fora da VM, sem
    permissão): o monitor segue sem esse check."""

    try:

        out = subprocess.run(
            [
                "journalctl", "-u", "runmind.service", "--no-pager", "-o", "cat",
                "--since", since.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            ],
            capture_output=True, text=True, timeout=60, check=False,
        )

    except (OSError, subprocess.SubprocessError):

        return None

    return out.stdout.splitlines() if out.returncode == 0 else None


# --- texto ---------------------------------------------------------------------------------------


def _icon(f: Facts, mine: list[Finding]) -> str:

    if f.external:

        return "⚪"

    if not f.due:

        return "🕐"

    if any(x.level == HIGH for x in mine):

        return "🔴"

    return "🟡" if mine else "🟢"


def _brief(f: Facts) -> str:

    if f.external:

        return "treinador externo (o plano é dele, o coach não gera)"

    if not f.due:

        return f"antes das {CHECK_HOUR}h de domingo no fuso do atleta: ainda não conferi"

    if f.plan_week != f.week:

        return "sem o plano da semana"

    sent = f"enviado {f.sent[0]:%H:%M}" if f.sent else "mensagem não encontrada"

    return f"{_km(f.new_km)} · {f.sessions} treinos · {sent}"


def render_report(
    facts: list[Facts],
    findings: list[Finding],
    per_plan: dict[str, float],
    total: float,
    journal: list[str] | None,
    texto: bool = False,
) -> str:
    """O relatório completo, pra tela: uma linha por atleta, os números por trás e cada alerta."""

    if not facts:

        return "Nenhum atleta ativo."

    by_profile: dict[str, list[Finding]] = {}

    for item in findings:

        by_profile.setdefault(item.profile, []).append(item)

    head = facts[0]

    lines = [
        f"CONFERÊNCIA DA GERAÇÃO DO PLANO DE DOMINGO — semana de {head.week:%d/%m} "
        f"(domingo {head.sunday:%d/%m}) · {len(facts)} atleta(s) ativo(s)",
        "",
    ]

    for f in facts:

        mine = by_profile.get(f.profile, [])

        lines.append(f"{_icon(f, mine)} {f.name} — {_brief(f)}")

        if f.plan_week == f.week and not f.external:

            bits = [f"estrutura do coach em {f.structured}/{f.sessions} sessões"]

            if f.plan_cost_brl:

                bits.append(f"IA do plano {_money(f.plan_cost_brl)}")

            lines.append("   " + " · ".join(bits))

            if f.last_planned_km or f.last_done_km:

                lines.append(
                    f"   semana passada: planejou {_km(f.last_planned_km)}, fez "
                    f"{_km(f.last_done_km)} (entregou: {'sim' if f.delivering else 'não'}) · maior "
                    f"treino do plano {_km(f.longest_plan_km)}, recente {_km(f.longest_recent_km)}"
                )

        for item in mine:

            icon = "🔴" if item.level == HIGH else "🟡"

            lines.append(f"   {icon} {TITLES.get(item.code, item.code)}: {item.text}")

        if texto and f.text:

            lines.append("")

            lines.append(f"   --- como o atleta recebeu (enviado {f.sent[-1]:%a %d/%m %H:%M}) ---")

            lines.extend(f"   {row}" for row in f.text.splitlines())

        lines.append("")

    general = by_profile.get("geral", [])

    for item in general:

        lines.append(f"🟡 {TITLES.get(item.code, item.code)}: {item.text}")

    plans = sum(per_plan.values())

    lines.append(
        f"IA desde o domingo 00:00 (fuso de cada atleta): {_money(total)} no total, "
        f"{_money(plans)} só nos planos."
    )

    if journal is None:

        lines.append("Journal do serviço: indisponível aqui (só na VM).")

    else:

        marks = [x for x in journal if any(mark in x for mark, _, _ in JOURNAL_MARKS)]

        lines.append(f"Journal do serviço: {len(marks)} marcador(es) de falha na geração.")

    due = [f for f in facts if not f.external and f.due]

    done = [f for f in due if f.plan_week == f.week and f.sent]

    lines.append(f"RESUMO: {len(done)} de {len(due)} entregues · {len(findings)} alerta(s).")

    return "\n".join(lines)


def format_message(
    facts: list[Facts],
    findings: list[Finding],
    total: float,
) -> str:
    """O aviso pro dono, em português de corredor: quantos planos saíram, o gasto, uma linha por
    atleta e, por alerta, o título, a frase com os números e UMA linha dizendo o que fazer."""

    if not facts:

        return "📋 Plano de domingo — nenhum atleta ativo pra conferir."

    names = {f.profile: f.name for f in facts}

    by_profile: dict[str, list[Finding]] = {}

    for item in sorted(findings, key=lambda x: (x.level != HIGH, x.profile)):

        by_profile.setdefault(item.profile, []).append(item)

    due = [f for f in facts if not f.external and f.due]

    done = [f for f in due if f.plan_week == f.week and f.sent]

    waiting = [f for f in facts if not f.external and not f.due]

    serious = sum(1 for x in findings if x.level == HIGH)

    lines = [
        f"📋 Plano de domingo — conferência da semana de {facts[0].week:%d/%m}",
        "",
        f"{len(done)} de {len(due)} atletas com o plano entregue · a IA gastou {_money(total)} "
        "desde domingo.",
    ]

    if waiting:

        lines.append(
            "🕐 Ainda não deu a hora no fuso de: " + ", ".join(f.name for f in waiting) + "."
        )

    if not findings:

        lines.append("Nenhum alerta: tudo certo. ✅")

    elif serious:

        lines.append(
            f"{len(findings)} alerta(s): {serious} sério(s) (🔴) e "
            f"{len(findings) - serious} pra acompanhar (🟡)."
        )

    else:

        lines.append(f"Nada urgente: {len(findings)} ponto(s) pra acompanhar (🟡).")

    lines.append("")

    for f in facts:

        mine = by_profile.get(f.profile, [])

        lines.append(f"{_icon(f, mine)} {f.name} — {_brief(f)}")

    for profile, items in by_profile.items():

        lines.append("")

        lines.append(names.get(profile, "Geral" if profile == "geral" else profile))

        for item in items:

            icon = "🔴" if item.level == HIGH else "🟡"

            lines.append(f"{icon} {TITLES.get(item.code, item.code)}")

            lines.append(item.text)

            action = ACTIONS.get(item.code)

            if action:

                lines.append(f"👉 {action}")

    lines.append("")

    lines.append(
        "É só um aviso: nada foi alterado. O texto que cada um recebeu: "
        "python -m app.application.monitoring.plan_generation_monitor --texto (na VM)."
    )

    return "\n".join(lines)


# --- ligação com os dados reais -------------------------------------------------------------------


class PlanGenerationMonitor:

    @staticmethod
    def athletes() -> list[str]:

        from app.infrastructure.persistence.runner_profile_repository import (
            RunnerProfileRepository,
        )

        return RunnerProfileRepository().list_active()

    @staticmethod
    def facts(profile: str, now: datetime) -> Facts:
        """Os números de UM atleta. Só leitura. O que a base não tiver fica no padrão (o check
        correspondente não dispara): um dado faltando nunca derruba a conferência dos outros."""

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.application.coach.writer.coach_persona import first_name
        from app.application.use_cases.load_runner_profile import LoadRunnerProfile
        from app.core.clock import use_athlete_timezone
        from app.infrastructure.persistence.coach_outbox_repository import (
            CoachOutboxRepository,
        )
        from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        tz = ZoneInfo(runner.timezone or DEFAULT_TZ)

        local = now.astimezone(tz)

        start = last_sunday(local)

        sunday = start.date()

        week = sunday + timedelta(days=1)

        f = Facts(
            profile=profile,
            name=first_name(runner.name) or profile,
            sunday=sunday,
            week=week,
            since=start.astimezone(UTC),
            due=local >= start.replace(hour=CHECK_HOUR),
            fresh=(local - start) < timedelta(days=FRESH_DAYS),
            external=bool(runner.external_coach),
        )

        plans = WeeklyPlanRepository()

        plan = plans.load(profile)

        if plan is not None:

            f.plan_week = plan.week_start

        if f.external or plan is None or plan.week_start != week:

            return f

        # o que o atleta recebeu: as mensagens de plano desde o domingo (o registro de envios é a
        # fonte — guarda o texto exato que saiu)
        sent: dict[datetime, str] = {}

        for key in {profile, getattr(runner, "id", None) or profile}:

            for entry in CoachOutboxRepository().recent(key, 50):

                text = str(entry.get("text") or "")

                stamp = _parse_ts(entry.get("timestamp"))

                if stamp is None or "plano da semana" not in text.lower()[:80]:

                    continue

                if stamp.astimezone(tz) >= start:

                    sent[stamp.astimezone(tz)] = text

        f.sent = sorted(sent)

        f.text = sent[f.sent[-1]] if f.sent else ""

        sessions = [s for s in plan.sessions if getattr(s, "kind", "run") in _RUN_KINDS]

        f.sessions = len(sessions)

        f.structured = sum(1 for s in sessions if (s.structure or "").strip())

        f.new_km = float(
            plan.weekly_volume or sum((s.effective_distance_km or 0.0) for s in sessions)
        )

        f.longest_plan_km = max(((s.effective_distance_km or 0.0) for s in sessions), default=0.0)

        f.is_deload = bool(plan.is_deload)

        f.deload_why = (plan.deload_why or "").strip()

        # o que ele fez na semana passada e o maior treino recente — os mesmos números que o coach
        # usa pra decidir "segurar" (AthleteDossier)
        try:

            data = AthleteDossier._inputs(profile, None, None, None, local.date())

            data.target_week = week

            f.delivering = AthleteDossier._is_delivering(data)

            closed = [
                w for w in AthleteDossier._ledger(data) if not w.in_progress and w.planned_km > 0
            ]

            if closed:

                f.last_planned_km = closed[-1].planned_km

                f.last_done_km = closed[-1].done_km

            _, longest = AthleteDossier.closed_weeks(data)

            # conferência no meio da semana: a última "fechada" ainda está em andamento
            if data.today < week - timedelta(days=1):

                longest = longest[:-1]

            f.longest_recent_km = max(longest[-RECENT_WEEKS:], default=0.0)

        except Exception as e:  # noqa: BLE001 — sem esses números os checks de corte/salto calam

            print(f"Monitor do plano: números da semana passada falharam p/ '{profile}': {e}")

        try:

            previous = next(
                (p for p in plans.history(profile) if p.week_start == week - timedelta(days=7)),
                None,
            )

            if previous is not None:

                f.repeated = repeated_sessions(plan.sessions, previous.sessions)

        except Exception as e:  # noqa: BLE001

            print(f"Monitor do plano: repetição falhou p/ '{profile}': {e}")

        return f

    @staticmethod
    def costs(facts: list[Facts]) -> tuple[dict[str, float], float]:
        """O gasto de IA desde o domingo de cada atleta: (planos por atleta, total de tudo)."""

        from app.infrastructure.persistence.token_usage_repository import TokenUsageRepository

        since = {f.profile: f.since for f in facts}

        floor = min(since.values(), default=None)

        per_plan: dict[str, float] = {}

        total = 0.0

        if floor is None:

            return per_plan, total

        repository = TokenUsageRepository()

        for file_profile in repository.profiles():

            for record in repository.read(file_profile):

                stamp = _parse_ts(record.get("ts"))

                if stamp is None or stamp < floor:

                    continue

                value = cost_brl(record)

                total += value

                owner = record.get("profile") or file_profile

                if record.get("label") in PLAN_LABELS and stamp >= since.get(owner, floor):

                    per_plan[owner] = per_plan.get(owner, 0.0) + value

        return per_plan, total


def run(send: bool, texto: bool = False, now: datetime | None = None) -> str:
    """Confere TODOS os atletas ativos. Sem `send`: só mostra (dry-run). Com `send`: avisa o dono
    (e mostra o mesmo na tela, pro log do cron). Devolve o aviso."""

    now = now or datetime.now(UTC)

    facts: list[Facts] = []

    findings: list[Finding] = []

    for profile in PlanGenerationMonitor.athletes():

        try:

            facts.append(PlanGenerationMonitor.facts(profile, now))

        except Exception as e:  # noqa: BLE001 — um atleta torto não derruba a conferência

            print(f"Monitor do plano: atleta '{profile}' falhou: {e}")

            findings.append(
                Finding(profile, "sem_conferencia", WATCH, f"Não consegui ler os dados dele: {e}")
            )

    per_plan, total = PlanGenerationMonitor.costs(facts)

    for f in facts:

        f.plan_cost_brl = per_plan.get(f.profile, 0.0)

        findings.extend(checks(f))

    findings.extend(cost_findings(per_plan, total))

    journal = read_journal(min(f.since for f in facts)) if facts else None

    if journal is not None:

        findings.extend(journal_findings(journal))

    findings.sort(key=lambda x: (x.level != HIGH, x.profile))

    print(render_report(facts, findings, per_plan, total, journal, texto))

    message = format_message(facts, findings, total)

    if not send:

        print("\n--- o aviso que iria pro Telegram do dono (com --send) ---\n")

        print(message)

        return message

    if asyncio.run(_send(message)):

        print(f"{now:%F %T} conferência do plano: aviso enviado ({len(findings)} alerta(s))")

    return message


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--send", action="store_true", help="avisa o dono no Telegram")

    parser.add_argument("--texto", action="store_true", help="mostra o texto que cada um recebeu")

    args = parser.parse_args()

    run(send=args.send, texto=args.texto)


if __name__ == "__main__":

    main()
