"""AUDITORIA DO COACH — roda na VM, só leitura, sobre o que o coach FEZ de
verdade nos últimos N dias. Procura as falhas que já aconteceram com atleta
real, pra cada uma virar correção na raiz:

- promessa sem entrega ("já estou preparando", "em instantes te envio") sem a
  ação que cumpre (João 06/09);
- atleta reclamando ("mas eu tinha falado", "você não mudou");
- cobrança de rotina/furo com o atleta relatando doença (Hélio 27/09);
- mensagem proativa repetida;
- cérebro do chat caindo no fallback;
- percepção: quantas corridas têm relato (relógio/resposta/conversa);
- plano da semana: gerado pela IA ou pelo fallback;
- erros da IA/tracebacks no log do serviço;
- dado absurdo: limiar muito mais rápido que o ritmo real (Hélio 4:07) ou
  ritmo-alvo mais rápido que o VO2 (Maurício 3:48);
- perfil × memória: dias pedidos na conversa ≠ dias do perfil (João).

    .venv/bin/python /tmp/coach_audit.py [--days 7]
(normalmente via ops/coach_audit.sh, que traz o relatório pro repo local)"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

BACKEND = Path.home() / "runmind" / "backend"

sys.path.insert(0, str(BACKEND))

STORAGE = BACKEND / "storage"

PROMISE = re.compile(
    r"(estou preparando|to preparando|tô preparando|em instantes|já te envio|"
    r"vou te mandar|vou te enviar|vou montar e te|te mando (o|a|já|em)|"
    r"estou montando|estou finalizando|em breve te envio|vou tentar|"
    r"vou (sincronizar|cancelar|pausar|pular|tirar|remover|atualizar|"
    r"refazer|mandar|enviar))",
    re.I,
)

COMPLAINT = re.compile(
    r"(mas eu (tinha|já|falei|disse)|você não (mudou|fez|mandou|aplicou|"
    r"atualizou)|já (tinha )?(falei|disse|avisei)|não (chegou|recebi|mudou)|"
    r"cadê|esqueceu|de novo\?|continua (errado|igual))",
    re.I,
)

# cobrança de verdade (não "não rolou, relaxa")
NAG = re.compile(
    r"(o que tá pegando|o que está pegando|furou|fura a|dá uma travada|"
    r"você fez \d+ de \d+|precisa caber na sua vida|cadê a constância)",
    re.I,
)

ILL = re.compile(r"(gripe|gripad|resfriad|doente|febre|virose|covid)", re.I)

_PT_DAYS = {
    "segunda": "Monday", "terça": "Tuesday", "terca": "Tuesday",
    "quarta": "Wednesday", "quinta": "Thursday", "sexta": "Friday",
    "sábado": "Saturday", "sabado": "Saturday", "domingo": "Sunday",
}


def _load(path: Path, default):

    try:

        return json.loads(path.read_text(encoding="utf-8"))

    except Exception:

        return default


def _day(stamp) -> date | None:

    try:

        return datetime.fromisoformat(str(stamp)).date()

    except ValueError:

        return None


def _pace(minutes: float | None) -> str:

    if not minutes:

        return "—"

    return f"{int(minutes)}:{round((minutes % 1) * 60):02d}"


def audit_profile(profile: str, since: date, lines: list[str]) -> list[str]:
    """Achados do atleta (e escreve o detalhe em `lines`)."""

    from app.application.history.metrics_resolver import MetricsResolver
    from app.application.history.weekly_buckets import activity_date
    from app.application.use_cases.build_training_goal import BuildTrainingGoal
    from app.application.use_cases.load_runner_profile import LoadRunnerProfile
    from app.domain.entities.training_history import TrainingHistory
    from app.domain.value_objects.sports import is_foot_sport
    from app.infrastructure.persistence.activity_archive_repository import (
        ActivityArchiveRepository,
    )
    from app.infrastructure.persistence.checkin_repository import CheckinRepository
    from app.infrastructure.persistence.session_rpe_repository import (
        SessionRpeRepository,
    )
    from app.infrastructure.persistence.weekly_plan_repository import (
        WeeklyPlanRepository,
    )

    findings: list[str] = []

    runner = LoadRunnerProfile.execute(profile)

    # ---------------------------------------------------------- conversa
    brain = [
        e for e in _load(STORAGE / "coach_brain_log" / f"{profile}.json", [])
        if (_day(e.get("ts")) or date.min) >= since
    ]

    for e in brain:

        types = {a.get("type") for a in (e.get("actions") or [])}

        say = str(e.get("say") or "")

        if PROMISE.search(say) and not (types - {None}):

            findings.append(
                f"PROMESSA SEM ENTREGA {e['ts'][:16]}: \"{say[:160]}\" "
                f"(ações: {sorted(t for t in types if t) or 'nenhuma'})"
            )

        if COMPLAINT.search(str(e.get("incoming") or "")):

            findings.append(
                f"RECLAMAÇÃO {e['ts'][:16]}: \"{str(e['incoming'])[:140]}\" → "
                f"coach: \"{say[:120]}\" (ações: "
                f"{sorted(t for t in types if t) or 'nenhuma'})"
            )

        if e.get("fallback"):

            findings.append(f"CÉREBRO CAIU NO FALLBACK {e['ts'][:16]}: \"{str(e.get('incoming'))[:100]}\"")

    # ---------------------------------------------------------- proativos
    outbox = [
        e for e in _load(STORAGE / "coach_outbox" / f"{profile}.json", [])
        if (_day(e.get("timestamp")) or date.min) >= since
    ]

    checkins = CheckinRepository().load(profile)

    # quando ele RELATOU doença (momento do relato, não só o dia)
    ill_at = [
        datetime.fromisoformat(c.at) for c in checkins
        if getattr(c, "illness", False) or ILL.search(getattr(c, "note", "") or "")
    ]

    for e in outbox:

        try:

            sent = datetime.fromisoformat(str(e.get("timestamp")))

        except ValueError:

            continue

        text = str(e.get("text") or "")

        sick = any(
            0 <= (sent - ill).total_seconds() <= 7 * 86400
            for ill in ill_at
            if (ill.tzinfo is None) == (sent.tzinfo is None)
        )

        if sick and NAG.search(text) and not ILL.search(text):

            findings.append(
                f"COBRANÇA COM ATLETA DOENTE {e['timestamp'][:16]}: "
                f"\"{' '.join(text.split())[:160]}\""
            )

    repeated = [
        t for t, n in Counter(
            " ".join(str(e.get("text") or "").split())[:200] for e in outbox
        ).items() if n > 1 and t
    ]

    for text in repeated:

        findings.append(f"MENSAGEM REPETIDA: \"{text[:120]}\"")

    # ---------------------------------------------------------- percepção
    activities = ActivityArchiveRepository().load_activities(profile)

    runs = [
        a for a in activities
        if is_foot_sport(a.sport) and activity_date(a) >= since
    ]

    rpes = [
        s for s in SessionRpeRepository().load_sessions(profile)
        if date.fromisoformat(s.day) >= since
    ]

    sources = Counter(getattr(s, "source", "resposta") for s in rpes)

    # ---------------------------------------------------------- plano
    plan = WeeklyPlanRepository().load(profile)

    if plan is not None and getattr(plan, "source", "") == "deterministico":

        findings.append(
            f"PLANO SEM IA: semana {plan.week_start:%d/%m} saiu do fallback "
            "determinístico"
        )

    # ---------------------------------------------------------- dado
    runs_all = sorted(
        (a for a in activities if is_foot_sport(a.sport) and a.average_speed > 0),
        key=lambda a: a.start_date, reverse=True,
    )[:30]

    history = TrainingHistory(activities=runs_all)

    goal = BuildTrainingGoal.execute(runner)

    try:

        metrics = MetricsResolver.resolve(runner, history)

        paces = [(1000 / a.average_speed) / 60 for a in runs_all if a.distance >= 2000]

        typical = median(paces) if paces else None

        if typical and metrics.threshold_pace and metrics.threshold_pace < typical * 0.75:

            findings.append(
                f"DADO SUSPEITO: limiar {_pace(metrics.threshold_pace)} × ritmo "
                f"típico {_pace(typical)} (mais de 25% mais rápido)"
            )

        if goal.target_time and goal.distance_km and metrics.vo2_pace:

            h, m, sec = ([0] + [int(x) for x in goal.target_time.split(":")])[-3:]

            target_pace = (h * 60 + m + sec / 60) / goal.distance_km

            # meta AMBICIOSA é legítima; SUSPEITA é bem além do VO2 de hoje
            # (Maurício 27/09: 3:48/km com VO2 5:26 — tempo herdado de outra prova)
            if target_pace < metrics.vo2_pace * 0.9:

                findings.append(
                    f"META SUSPEITA: alvo {goal.target_time} nos "
                    f"{goal.distance_km:g} km (~{_pace(target_pace)}/km) mais "
                    f"rápido que o VO2 atual ({_pace(metrics.vo2_pace)}/km) — "
                    "confira se o tempo não é de outra prova"
                )

    except Exception as e:

        findings.append(f"(não deu pra checar ritmos: {e})")

    # ---------------------------------------------------------- perfil × memória
    memory = [
        m for m in _load(STORAGE / "memory" / f"{profile}.json", [])
        if m.get("status") == "active" and m.get("category") == "disponibilidade"
        and not re.search(r"\blong(ão|ao|o)\b", m.get("content", ""), re.I)
    ]

    if memory:

        latest = max(memory, key=lambda m: m.get("created_at", ""))

        said = {
            en for pt, en in _PT_DAYS.items()
            if re.search(rf"\b{pt}", latest.get("content", ""), re.I)
        }

        if len(said) >= 2 and said != set(runner.preferred_running_days or []):

            findings.append(
                f"PERFIL × MEMÓRIA: memória ({latest.get('created_at', '')[:10]}) "
                f"diz dias {sorted(said)} e o perfil {runner.preferred_running_days} "
                f"— \"{latest.get('content', '')[:120]}\""
            )

    lines.append(f"\n## {runner.name} ({profile})")

    lines.append(
        f"- conversa: {len(brain)} decisões do cérebro; proativos: {len(outbox)}; "
        f"corridas: {len(runs)}; percepção registrada: {len(rpes)} "
        f"({dict(sources) or 'nenhuma'})"
    )

    lines.append(
        f"- plano vigente: semana {plan.week_start:%d/%m} ({plan.source}, fase "
        f"{plan.phase})" if plan is not None else "- plano vigente: nenhum"
    )

    lines.append(f"- meta: {runner.goal} | alvo {goal.target_time} | dias {runner.preferred_running_days}")

    for f in findings:

        lines.append(f"- ⚠️ {f}")

    if not findings:

        lines.append("- ✅ nada a corrigir")

    return findings


# ------------------------------------------------------------------ placar
# "Está melhor do que antes?" respondido por NÚMERO, toda segunda: as últimas
# semanas FECHADAS (seg–dom) de cada atleta lado a lado. As mudanças grandes do
# coach entraram em 26-27/09 — a semana de 28/09 é a 1ª "depois".
PLACAR_WEEKS = 4


def _coach_errors(profile: str, start: date, end: date) -> int:
    """Erros do coach na semana: promessa sem ação, cobrança com atleta
    doente, mensagem repetida (as mesmas regras dos achados)."""

    from app.infrastructure.persistence.checkin_repository import CheckinRepository

    def within(stamp) -> bool:

        d = _day(stamp)

        return d is not None and start <= d <= end

    errors = 0

    for e in _load(STORAGE / "coach_brain_log" / f"{profile}.json", []):

        types = {a.get("type") for a in (e.get("actions") or [])} - {None}

        if within(e.get("ts")) and PROMISE.search(str(e.get("say") or "")) and not types:

            errors += 1

    outbox = [
        e for e in _load(STORAGE / "coach_outbox" / f"{profile}.json", [])
        if within(e.get("timestamp"))
    ]

    ill_at = [
        datetime.fromisoformat(c.at) for c in CheckinRepository().load(profile)
        if getattr(c, "illness", False) or ILL.search(getattr(c, "note", "") or "")
    ]

    for e in outbox:

        try:

            sent = datetime.fromisoformat(str(e.get("timestamp")))

        except ValueError:

            continue

        text = str(e.get("text") or "")

        sick = any(
            0 <= (sent - ill).total_seconds() <= 7 * 86400
            for ill in ill_at
            if (ill.tzinfo is None) == (sent.tzinfo is None)
        )

        if sick and NAG.search(text) and not ILL.search(text):

            errors += 1

    texts = Counter(" ".join(str(e.get("text") or "").split())[:200] for e in outbox)

    errors += sum(n - 1 for t, n in texts.items() if t and n > 1)

    return errors


def placar(profile: str, today: date, lines: list[str]) -> None:
    """Tabela das últimas semanas fechadas: erros do coach, aderência ao
    plano, km, percepção coletada e FC de repouso média (recuperação)."""

    from app.application.history.weekly_buckets import activity_date
    from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
    from app.domain.value_objects.sports import is_foot_sport
    from app.infrastructure.persistence.activity_archive_repository import (
        ActivityArchiveRepository,
    )
    from app.infrastructure.persistence.checkin_repository import CheckinRepository
    from app.infrastructure.persistence.garmin_health_repository import (
        GarminHealthRepository,
    )
    from app.infrastructure.persistence.session_rpe_repository import (
        SessionRpeRepository,
    )
    from app.infrastructure.persistence.weekly_plan_repository import (
        WeeklyPlanRepository,
    )

    repo = WeeklyPlanRepository()

    plans = {p.week_start: p for p in repo.history(profile)}

    current = repo.load(profile)

    if current is not None:

        plans[current.week_start] = current

    runs = [
        a for a in ActivityArchiveRepository().load_activities(profile)
        if is_foot_sport(a.sport)
    ]

    rpes = SessionRpeRepository().load_sessions(profile)

    checkins = CheckinRepository().load(profile)

    health = GarminHealthRepository().load(profile)

    this_monday = today - timedelta(days=today.weekday())

    rows = []

    for back in range(PLACAR_WEEKS, 0, -1):

        start = this_monday - timedelta(days=7 * back)

        end = start + timedelta(days=6)

        week_runs = [a for a in runs if start <= activity_date(a) <= end]

        km = sum(a.distance for a in week_runs) / 1000

        plan = plans.get(start)

        if plan is not None and plan.sessions:

            done = len(WeeklyPlanMatcher.fulfilled_days(plan, week_runs))

            adherence = f"{done}/{len({x.day for x in plan.sessions})}"

        else:

            adherence = "—"

        felt = sum(1 for r in rpes if start <= date.fromisoformat(r.day) <= end)

        felt += sum(1 for c in checkins if start <= date.fromisoformat(c.day) <= end)

        rhr = [
            h.resting_hr for h in health
            if h.resting_hr and start <= date.fromisoformat(h.date) <= end
        ]

        rhr_txt = f"{sum(rhr) / len(rhr):.0f}" if rhr else "—"

        rows.append(
            f"| {start:%d/%m} | {_coach_errors(profile, start, end)} | "
            f"{adherence} | {km:.1f} | {felt} | {rhr_txt} |"
        )

    lines.append("- placar (semanas fechadas, seg–dom):")

    lines.append("")

    lines.append("  | semana | erros do coach | treinos feitos | km | percepção | FC repouso |")

    lines.append("  |---|---|---|---|---|---|")

    lines.extend(f"  {r}" for r in rows)


def service_errors(days: int) -> list[str]:

    try:

        out = subprocess.run(
            [
                "journalctl", "-u", "runmind.service", "--since",
                f"{days} days ago", "--no-pager",
            ],
            capture_output=True, text=True, timeout=60,
        ).stdout

    except Exception as e:

        return [f"(journal indisponível: {e})"]

    counts = Counter()

    for line in out.splitlines():

        for label, pattern in (
            ("fallback determinístico do plano", "fallback determinístico"),
            ("IA falhou (qualquer voz)", "IA falhou"),
            ("traceback", "Traceback"),
            ("me embananei", "embananei"),
            ("dossiê: seção falhou", "Dossiê ("),
        ):

            if pattern in line:

                counts[label] += 1

    return [f"{label}: {n}" for label, n in counts.most_common()]


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--days", type=int, default=7)

    args = parser.parse_args()

    from app.core.clock import today_local
    from app.infrastructure.persistence.runner_profile_repository import (
        RunnerProfileRepository,
    )

    today = today_local()

    since = today - timedelta(days=args.days)

    lines = [
        f"# Auditoria do coach — {since:%d/%m} a {today:%d/%m/%Y}",
    ]

    total = 0

    for profile in RunnerProfileRepository().list_active():

        try:

            total += len(audit_profile(profile, since, lines))

            placar(profile, today, lines)

        except Exception as e:

            lines.append(f"\n## {profile}\n- (auditoria falhou: {e})")

    lines.append("\n## Serviço (log da VM)")

    lines.extend(f"- {e}" for e in service_errors(args.days) or ["- limpo"])

    lines.insert(1, f"\n**{total} achado(s) nos atletas.**")

    print("\n".join(lines))


if __name__ == "__main__":

    main()
