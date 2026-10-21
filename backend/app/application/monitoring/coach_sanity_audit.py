"""AUDITORIA DE SANIDADE DO COACH — roda todo dia, SEM IA, e avisa o dono no Telegram SÓ quando há
achado novo. Procura o que o coach VÊ nos dados mas o atleta só denuncia reclamando.

A auditoria semanal (`ops/coach_audit.py`) caça SINTOMAS em mensagens: promessa sem entrega,
reclamação, erro engolido. Não olha o ESTADO do coach contra os DADOS nem a falta de evolução — e
foi por aí que o Leonardo ficou semanas com treino fraco sem ninguém saber (21/10): o treino do
próprio coach "Ritmo de Prova" lido como prova (modo pós-prova trava o "puxar"), esforço percebido
≤3/10 em 6 de 7 corridas, 0% do tempo em zona forte e um pedido de "mais" que não mudou a dose.

Cada achado vem em português simples, com os números. O alerta não muda NADA sozinho (só avisa) e
cada achado só volta a ser avisado depois de `COOLDOWN_DAYS` — sem ruído diário. Os checks são
puros (recebem números) e testados offline; `audit` só os liga aos dados reais.

    python -m app.application.monitoring.coach_sanity_audit          # mostra tudo (dry-run)
    python -m app.application.monitoring.coach_sanity_audit --send     # avisa o dono (cron)

Ver [[project_atleta_leonardo]] e [[project_rota_ate_a_meta]]."""

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# --- limiares (todos em um lugar; o alerta é pra OLHAR, não pra decidir) -------------------------

# cada achado só volta a ser avisado depois disto
COOLDOWN_DAYS = 7

# esforço baixo o tempo todo: relatos de esforço nos últimos 28 dias, mínimo e fração ≤3/10
RPE_WINDOW_DAYS = 28
RPE_MIN_REPORTS = 5
RPE_EASY = 3
RPE_EASY_SHARE = 0.8

# com prova datada e meta de tempo entre estas semanas de distância, esforço baixo pesa
EFFORT_WEEKS = (3, 12)

# pedido de mais carga sem resposta: dias desde o pedido e quanto a dose precisa ter subido
ASK_MIN_DAYS = 10
ASK_WEEK_GAIN = 1.15
ASK_LONG_GAIN = 1.10

# rota até a meta: a prova está perto E ainda falta tanto
PATH_WEEKS_LEFT = 8
PATH_LONG_GAP_KM = 1.5
PATH_WEEK_GAP_KM = 6.0

# forma estável há pelo menos estas semanas, com a prova a até tantas semanas
STAGNANT_WEEKS = 6
STAGNANT_RACE_WEEKS = 12

# o "pós-prova" do coach vale por este número de semanas (deload_analyzer._POST_RACE_GRACE_WEEKS)
POST_RACE_WEEKS = 3

HIGH = "alto"
WATCH = "atenção"


@dataclass(slots=True)
class Finding:

    profile: str
    code: str
    level: str
    text: str


# --- os checks (puros) ---------------------------------------------------------------------------


def _fmt_date(day: date) -> str:

    return f"{day:%d/%m}"


def unbacked_race(
    profile: str, event, result_dates: list[date], list_dates: list[date],
) -> Finding | None:
    """O coach acha que houve uma PROVA recente (modo pós-prova: sem sinal de "puxar" nem
    descarga) sem nenhuma prova na lista do app nem resultado registrado naquela data."""

    if event is None or event.weeks_ago > POST_RACE_WEEKS:

        return None

    near = [d for d in (*result_dates, *list_dates) if abs((d - event.date).days) <= 1]

    if near:

        return None

    return Finding(
        profile, "prova_sem_lastro", HIGH,
        f"O coach acha que \"{event.name}\" ({_fmt_date(event.date)}) foi uma PROVA e está em "
        "modo pós-prova (sem sinal de \"puxar\" nem descarga) — mas não há prova nessa data na "
        "lista do app nem resultado registrado. Confira se não é um treino com \"prova\" no nome.",
    )


def low_effort(
    profile: str, rpes: list[int], hard_pct: int | None, weeks_left: int | None,
    target_time: str | None, race_label: str,
) -> Finding | None:
    """Esforço percebido baixo em quase tudo E 0% do tempo em zona forte, com prova datada e meta
    de tempo a poucas semanas: o treino pode estar leve demais pro que a meta pede (ou é base
    deliberada — por isso é pra OLHAR)."""

    if weeks_left is None or not target_time:

        return None

    if not (EFFORT_WEEKS[0] <= weeks_left <= EFFORT_WEEKS[1]) or hard_pct != 0:

        return None

    if len(rpes) < RPE_MIN_REPORTS:

        return None

    easy = sum(1 for r in rpes if r <= RPE_EASY)

    if easy / len(rpes) < RPE_EASY_SHARE:

        return None

    return Finding(
        profile, "esforco_baixo", WATCH,
        f"Esforço percebido ≤{RPE_EASY}/10 em {easy} de {len(rpes)} corridas e 0% do tempo em "
        f"zona forte, com {race_label} em {weeks_left} semanas (meta {target_time}). O treino "
        "pode estar leve demais pro que a meta pede — ou ser base de propósito: vale olhar.",
    )


def asked_more_unanswered(
    profile: str, asks: list, since: dict | None, today: date, body_tired: bool,
) -> Finding | None:
    """Ele pediu mais carga e, depois de `ASK_MIN_DAYS`, a dose (km/semana e maior treino) não
    subiu — sem o corpo dele justificar. É o erro de ignorar em silêncio."""

    if not asks or since is None or body_tired:

        return None

    first = asks[0]

    days = (today - first.day).days

    if days < ASK_MIN_DAYS:

        return None

    week_up = since["after_week"] >= since["before_week"] * ASK_WEEK_GAIN

    long_up = since["after_long"] > since["before_long"] * ASK_LONG_GAIN

    if week_up or long_up:

        return None

    return Finding(
        profile, "pediu_mais_sem_resposta", HIGH,
        f"Em {_fmt_date(first.day)} ele disse \"{first.quote}\" e, há {days} dias, a dose não "
        f"subiu: antes ~{since['before_week']:.0f} km/semana e maior treino "
        f"{since['before_long']:.1f} km; depois ~{since['after_week']:.0f} km/semana e maior "
        f"treino {since['after_long']:.1f} km. O corpo dele não justifica segurar.",
    )


def path_gap(profile: str, path) -> Finding | None:
    """Pro passo atual, a prova chega perto e o preparo fica abaixo da faixa de referência."""

    if path is None or path.weeks_left > PATH_WEEKS_LEFT:

        return None

    gaps = []

    if path.long_gap >= PATH_LONG_GAP_KM:

        gaps.append(f"~{round(path.long_gap)} km no longão")

    if path.week_gap >= PATH_WEEK_GAP_KM:

        gaps.append(f"~{round(path.week_gap)} km por semana")

    if not gaps:

        return None

    return Finding(
        profile, "rota_abaixo_da_faixa", WATCH,
        f"Faltam {path.weeks_left} semanas pra prova e, no passo das últimas semanas, ele chega "
        f"com longão de ~{path.projected_long:.0f} km e ~{path.projected_week:.0f} km/semana "
        f"(referência: {path.long_ref[0]}-{path.long_ref[1]} km e "
        f"{path.week_ref[0]}-{path.week_ref[1]} km/semana): faltam {' e '.join(gaps)}.",
    )


def stagnant_form(
    profile: str, direction: str | None, weeks: int, weeks_left: int | None,
) -> Finding | None:
    """Forma estável há semanas com a prova perto: o plano não está rendendo evolução."""

    if direction != "STABLE" or weeks < STAGNANT_WEEKS:

        return None

    if weeks_left is None or weeks_left > STAGNANT_RACE_WEEKS:

        return None

    return Finding(
        profile, "forma_estagnada", WATCH,
        f"A forma está estável há ~{weeks} semanas (economia aeróbica sem melhorar) com a prova "
        f"em {weeks_left} semanas.",
    )


# --- ligação com os dados reais -------------------------------------------------------------------


class CoachSanityAudit:

    @staticmethod
    def athletes() -> list[str]:

        from app.infrastructure.persistence.runner_profile_repository import (
            RunnerProfileRepository,
        )

        return RunnerProfileRepository().list_active()

    @staticmethod
    def audit(profile: str, today: date | None = None) -> list[Finding]:
        """Todos os checks de UM atleta. Cada check é independente e best-effort: um dado
        faltando nunca derruba os outros."""

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.core.clock import today_local

        today = today or today_local()

        data = AthleteDossier._inputs(profile, None, None, None, today)

        findings: list[Finding] = []

        def run(check):

            try:

                found = check(data)

                if found is not None:

                    findings.append(found)

            except Exception as e:  # noqa: BLE001 — um check torto não derruba a auditoria

                print(f"Sanidade: check falhou p/ '{profile}': {e}")

        run(lambda d: CoachSanityAudit._check_race(d))
        run(lambda d: CoachSanityAudit._check_effort(d))
        run(lambda d: CoachSanityAudit._check_asked_more(d))
        run(lambda d: CoachSanityAudit._check_path(d))
        run(lambda d: CoachSanityAudit._check_form(d))

        return findings

    @staticmethod
    def _check_race(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.application.history.race_detector import RaceDetector
        from app.infrastructure.persistence.race_result_repository import (
            RaceResultRepository,
        )

        results = RaceResultRepository().load(data.profile)

        event = RaceDetector.most_recent(data.activities, data.today, past_results=results)

        result_dates = [
            RaceDetector._parse_date(r.get("date")) for r in results if r.get("date")
        ]

        list_dates = [
            RaceDetector._parse_date(r.get("date"))
            for r in AthleteDossier._races(data)
            if r.get("date")
        ]

        return unbacked_race(
            data.profile,
            event,
            [d for d in result_dates if d],
            [d for d in list_dates if d],
        )

    @staticmethod
    def _rpes(data) -> list[int]:

        from app.infrastructure.persistence.session_rpe_repository import (
            SessionRpeRepository,
        )

        cutoff = data.today - timedelta(days=RPE_WINDOW_DAYS)

        return [
            s.rpe
            for s in SessionRpeRepository().load_sessions(data.profile)
            if s.rpe is not None and date.fromisoformat(s.day) >= cutoff
        ]

    @staticmethod
    def _check_effort(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        target = AthleteDossier._route_goal(data, data.today)

        if target is None:

            return None

        _distance, target_time, race_date = target

        weeks_left = (race_date - data.today).days // 7

        label = (
            getattr(data.goal, "race_label", None) or "a prova"
        )

        return low_effort(
            data.profile,
            CoachSanityAudit._rpes(data),
            AthleteDossier._hard_pct(data),
            weeks_left,
            target_time,
            label,
        )

    @staticmethod
    def _check_asked_more(data) -> Finding | None:

        from app.application.history import athlete_asks_more as asks_more
        from app.domain.entities.body_reading import BODY_RECOVERY_FLAG, BODY_STRAINED
        from app.infrastructure.persistence.checkin_repository import CheckinRepository
        from app.infrastructure.persistence.conversation_repository import (
            ConversationRepository,
        )

        asks = asks_more.find(
            ConversationRepository().load(data.profile),
            CheckinRepository().load(data.profile),
            data.today,
        )

        if not asks:

            return None

        since = asks_more.dose_since(data.activities, asks[0].day, data.today)

        body = getattr(data.reading, "body_state", None)

        return asked_more_unanswered(
            data.profile, asks, since, data.today,
            body_tired=body in (BODY_STRAINED, BODY_RECOVERY_FLAG),
        )

    @staticmethod
    def _check_path(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        return path_gap(data.profile, AthleteDossier.route_path(data))

    @staticmethod
    def _check_form(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        evolution = AthleteDossier._form_of(data)

        if evolution is None or evolution.stale or not evolution.has_data:

            return None

        target = AthleteDossier._route_goal(data, data.today)

        weeks_left = (target[2] - data.today).days // 7 if target else None

        weeks = evolution.ef.weeks_covered if evolution.ef is not None else 0

        return stagnant_form(data.profile, evolution.direction, weeks, weeks_left)

    @staticmethod
    def audit_all(today: date | None = None) -> list[Finding]:

        out: list[Finding] = []

        for profile in CoachSanityAudit.athletes():

            try:

                out.extend(CoachSanityAudit.audit(profile, today))

            except Exception as e:  # noqa: BLE001

                print(f"Sanidade: atleta '{profile}' falhou: {e}")

        return out


# --- aviso (cooldown + mensagem + envio) ---------------------------------------------------------


class SanityState:
    """Quando cada achado foi avisado pela última vez — storage/sanity_audit/state.json."""

    def __init__(self, path: Path | None = None):

        self.path = path or (
            Path(__file__).resolve().parents[3] / "storage" / "sanity_audit" / "state.json"
        )

    def load(self) -> dict:

        if not self.path.exists():

            return {}

        try:

            return json.loads(self.path.read_text(encoding="utf-8"))

        except (OSError, ValueError):

            return {}

    def save(self, state: dict) -> None:

        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8",
        )


def _key(finding: Finding) -> str:

    return f"{finding.profile}:{finding.code}"


def fresh(findings: list[Finding], state: dict, today: date) -> list[Finding]:
    """Só os achados que ainda não foram avisados nos últimos `COOLDOWN_DAYS`."""

    out = []

    for finding in findings:

        last = state.get(_key(finding))

        if last and (today - date.fromisoformat(last)).days < COOLDOWN_DAYS:

            continue

        out.append(finding)

    return out


def _name(profile: str) -> str:

    try:

        from app.application.coach.writer.coach_persona import first_name
        from app.application.use_cases.load_runner_profile import LoadRunnerProfile

        return first_name(LoadRunnerProfile.execute(profile).name) or profile

    except Exception:  # noqa: BLE001

        return profile


def format_message(findings: list[Finding], names: dict[str, str] | None = None) -> str:
    """O aviso pro dono: um bloco por atleta, 🔴 alto antes de 🟡 atenção."""

    names = names or {}

    by_profile: dict[str, list[Finding]] = {}

    for finding in sorted(findings, key=lambda f: (f.level != HIGH, f.profile)):

        by_profile.setdefault(finding.profile, []).append(finding)

    lines = [f"🔎 Auditoria de sanidade do coach — {len(findings)} achado(s) novo(s)", ""]

    for profile, items in by_profile.items():

        lines.append(f"{names.get(profile, profile)}")

        for item in items:

            lines.append(f"{'🔴' if item.level == HIGH else '🟡'} {item.text}")

        lines.append("")

    lines.append(
        "É só um aviso: nada foi alterado. O dossiê e o plano do atleta mostram o que o coach "
        "está vendo."
    )

    return "\n".join(lines)


async def _send(message: str) -> bool:

    from app.application.notifications.notification_service import (
        TELEGRAM,
        NotificationService,
    )
    from app.core.config import get_settings

    admin_id = get_settings().admin_telegram_id

    if not admin_id:

        print("Sem ADMIN_TELEGRAM_ID: nada enviado.")

        return False

    await NotificationService.send_to(channel=TELEGRAM, address=admin_id, message=message)

    return True


def run(send: bool, today: date | None = None, state: SanityState | None = None) -> str:
    """Audita todos os atletas. Sem `send`: só mostra (dry-run, ignora o cooldown). Com `send`:
    avisa o dono dos achados NOVOS e grava quando avisou. Devolve o que foi mostrado/enviado."""

    from app.core.clock import today_local

    today = today or today_local()

    state = state or SanityState()

    findings = CoachSanityAudit.audit_all(today)

    stored = state.load()

    pending = fresh(findings, stored, today)

    names = {f.profile: _name(f.profile) for f in findings}

    if not send:

        shown = format_message(findings, names) if findings else "Sem achados."

        print(shown)

        print(f"\n({len(pending)} de {len(findings)} seriam enviados agora — fora do cooldown)")

        return shown

    if not pending:

        print(f"{today} sanidade: sem achados novos ({len(findings)} em cooldown)")

        return ""

    message = format_message(pending, names)

    if asyncio.run(_send(message)):

        for finding in pending:

            stored[_key(finding)] = today.isoformat()

        state.save(stored)

        print(f"{today} sanidade: {len(pending)} achado(s) enviado(s) ao admin")

    return message


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--send", action="store_true")

    args = parser.parse_args()

    run(send=args.send)


if __name__ == "__main__":

    main()
