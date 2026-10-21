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

# --- checks que valem pra TODOS (não dependem de prova com data) ---------------------------------

# rodagem leve/regenerativa é metade ou mais das sessões prescritas, com meta de tempo
EASY_SHARE_MAX = 0.5
EASY_WINDOW_WEEKS = 6
EASY_MIN_SESSIONS = 8

# nenhum estímulo forte FEITO há tantos dias, correndo normalmente, com meta de tempo
NO_QUALITY_DAYS = 21
NO_QUALITY_MIN_RUNS = 6

# volume e maior treino sem mudar por estas semanas fechadas, com o plano em dia
STALL_WEEKS = 4
STALL_KM_SPREAD = 0.12
STALL_LONG_SPREAD_KM = 1.0
STALL_MIN_ADHERENCE = 0.85

# cumpriu menos que isto do plano nas últimas semanas (mínimo de sessões planejadas)
ADHERENCE_LOW = 0.6
ADHERENCE_MIN_PLANNED = 6
ADHERENCE_WEEKS = 3

# sem correr há tantos dias e sem doença registrada
STOPPED_DAYS = 14

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


@dataclass(slots=True)
class Snapshot:
    """Os números de um atleta no painel de segunda."""

    profile: str
    km_week: float | None
    long_km: float | None
    adherence: float | None
    next_race: str | None


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


def easy_heavy(
    profile: str, easy: int, total: int, target_time: str | None,
) -> Finding | None:
    """Metade ou mais das sessões prescritas é rodagem leve/regenerativa e ele tem META DE TEMPO:
    o plano pode estar com treino demais sem estímulo e sem função pra evoluir."""

    if not target_time or total < EASY_MIN_SESSIONS or easy / total < EASY_SHARE_MAX:

        return None

    return Finding(
        profile, "rodagem_demais", WATCH,
        f"{easy} de {total} sessões prescritas nas últimas {EASY_WINDOW_WEEKS} semanas "
        f"({easy / total:.0%}) são rodagem leve ou regenerativa, e ele tem meta de tempo "
        f"({target_time}). Vale olhar se o plano tem estímulo e função suficientes pra evoluir.",
    )


def no_quality(
    profile: str, days_since: int | None, runs: int, target_time: str | None,
) -> Finding | None:
    """Correndo normalmente, com meta de tempo, mas sem NENHUM estímulo forte feito (limiar, VO2,
    ritmo de prova, fartlek, progressivo) há semanas. `days_since` None = nenhum nas últimas 8."""

    if not target_time or runs < NO_QUALITY_MIN_RUNS:

        return None

    if days_since is not None and days_since < NO_QUALITY_DAYS:

        return None

    since = f"há {days_since} dias" if days_since is not None else "nas últimas 8 semanas"

    return Finding(
        profile, "sem_estimulo_forte", WATCH,
        f"Nenhum estímulo forte (limiar, VO2, ritmo de prova, fartlek ou progressivo) feito "
        f"{since}, com {runs} corridas nos últimos {NO_QUALITY_DAYS} dias e meta de "
        f"{target_time}.",
    )


def stalled_plan(
    profile: str, weekly_km: list[float], longest_km: list[float], adherence: float | None,
) -> Finding | None:
    """Volume e maior treino praticamente iguais por `STALL_WEEKS` semanas fechadas com o plano em
    dia: o plano parou de progredir (é pra olhar: pode ser manutenção de propósito)."""

    weeks = weekly_km[-STALL_WEEKS:]

    longs = longest_km[-STALL_WEEKS:]

    if len(weeks) < STALL_WEEKS or min(weeks) <= 0:

        return None

    if adherence is not None and adherence < STALL_MIN_ADHERENCE:

        return None

    mean = sum(weeks) / len(weeks)

    if (max(weeks) - min(weeks)) / mean > STALL_KM_SPREAD:

        return None

    if max(longs) - min(longs) > STALL_LONG_SPREAD_KM:

        return None

    return Finding(
        profile, "plano_parado", WATCH,
        f"O volume (~{mean:.0f} km/semana, variando só {(max(weeks) - min(weeks)) / mean:.0%}) e "
        f"o maior treino (~{max(longs):.0f} km) não mudam há {STALL_WEEKS} semanas com o plano "
        "em dia: o plano parou de progredir.",
    )


def low_adherence(profile: str, done: int, planned: int, weeks: int) -> Finding | None:
    """Cumpriu pouco do plano nas últimas semanas: o plano pode estar desalinhado da rotina dele
    (dias, volume ou tipo) — prescrever o que ele não faz não evolui ninguém."""

    if planned < ADHERENCE_MIN_PLANNED or weeks < ADHERENCE_WEEKS:

        return None

    if done / planned >= ADHERENCE_LOW:

        return None

    return Finding(
        profile, "aderencia_baixa", WATCH,
        f"Cumpriu {done} de {planned} treinos nas últimas {weeks} semanas ({done / planned:.0%}): "
        "o plano pode estar desalinhado da rotina dele.",
    )


def stopped_running(profile: str, days_since: int | None, ill: bool) -> Finding | None:
    """Sem correr há semanas e sem doença registrada: pausa combinada ou afastamento?"""

    if ill or days_since is None or days_since < STOPPED_DAYS:

        return None

    return Finding(
        profile, "parou_de_correr", HIGH,
        f"A última corrida foi há {days_since} dias e não há doença registrada: confira se há uma "
        "pausa combinada ou se ele se afastou.",
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
        run(lambda d: CoachSanityAudit._check_easy_heavy(d))
        run(lambda d: CoachSanityAudit._check_no_quality(d))
        run(lambda d: CoachSanityAudit._check_stalled(d))
        run(lambda d: CoachSanityAudit._check_adherence(d))
        run(lambda d: CoachSanityAudit._check_stopped(d))

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
    def _races_ahead(data) -> list[dict]:
        """TODAS as provas à frente (A, B e C), da mais próxima pra mais distante, cada uma com o
        seu alvo — não só a principal: o 15 km preparatório a 8 semanas pesa mesmo com a meia (A)
        a 23. Sem lista, a prova do perfil."""

        from app.application.coach.context.athlete_dossier import AthleteDossier

        ahead = []

        for race in AthleteDossier._races(data):

            if not race.get("date"):

                continue

            when = date.fromisoformat(race["date"])

            if when > data.today:

                ahead.append({
                    "date": when,
                    "km": race.get("distance_km"),
                    "target": race.get("target_time"),
                    "role": race.get("priority") or race.get("priority_effective"),
                })

        goal = data.goal

        if not ahead and getattr(goal, "race_date", None) and goal.race_date > data.today:

            ahead.append({
                "date": goal.race_date, "km": goal.distance_km,
                "target": goal.target_time, "role": None,
            })

        return sorted(ahead, key=lambda r: r["date"])

    @staticmethod
    def _race_label(race: dict) -> str:

        km = f"{race['km']:g} km" if race.get("km") else "prova"

        role = {"A": "principal", "B": "preparatória", "C": "de treino"}.get(race.get("role") or "")

        return f"a prova de {km} em {race['date']:%d/%m}" + (f" ({role})" if role else "")

    @staticmethod
    def _check_effort(data) -> Finding | None:
        """O esforço baixo pesa contra a prova MAIS PRÓXIMA dentro da janela — qualquer papel."""

        from app.application.coach.context.athlete_dossier import AthleteDossier

        for race in CoachSanityAudit._races_ahead(data):

            weeks_left = (race["date"] - data.today).days // 7

            if EFFORT_WEEKS[0] <= weeks_left <= EFFORT_WEEKS[1] and race.get("target"):

                return low_effort(
                    data.profile,
                    CoachSanityAudit._rpes(data),
                    AthleteDossier._hard_pct(data),
                    weeks_left,
                    race["target"],
                    CoachSanityAudit._race_label(race),
                )

        return None

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

        races = CoachSanityAudit._races_ahead(data)

        weeks_left = (races[0]["date"] - data.today).days // 7 if races else None

        weeks = evolution.ef.weeks_covered if evolution.ef is not None else 0

        return stagnant_form(data.profile, evolution.direction, weeks, weeks_left)

    # --- os checks que não dependem de prova -------------------------------------------------

    @staticmethod
    def _plans(data) -> list:

        from app.infrastructure.persistence.weekly_plan_repository import (
            WeeklyPlanRepository,
        )

        repository = WeeklyPlanRepository()

        plans = list(repository.history(data.profile))

        current = repository.load(data.profile)

        if current is not None:

            plans.append(current)

        return plans

    @staticmethod
    def _check_easy_heavy(data) -> Finding | None:

        from app.application.history.stimulus_ledger import EASY, StimulusLedger

        start = data.today - timedelta(weeks=EASY_WINDOW_WEEKS)

        easy = total = 0

        for plan in {p.week_start: p for p in CoachSanityAudit._plans(data)}.values():

            for session in plan.sessions:

                if getattr(session, "kind", "run") not in ("run", "walk", "run_walk"):

                    continue

                if not start <= plan.session_date(session) <= data.today:

                    continue

                total += 1

                easy += StimulusLedger.classify(session.workout_type) == EASY

        return easy_heavy(data.profile, easy, total, getattr(data.goal, "target_time", None))

    @staticmethod
    def _check_no_quality(data) -> Finding | None:

        from app.application.history import stimulus_ledger as ledger
        from app.application.history.weekly_buckets import activity_date
        from app.domain.value_objects.sports import is_run_sport

        quality = {
            ledger.RACE_PACE, ledger.HILLS, ledger.FARTLEK, ledger.THRESHOLD, ledger.VO2,
            ledger.PROGRESSION,
        }

        stats = ledger.StimulusLedger.families(
            CoachSanityAudit._plans(data), data.activities, data.today,
        )

        last = [s.last_done for f, s in stats.items() if f in quality and s.last_done]

        days_since = (data.today - max(last)).days if last else None

        since = data.today - timedelta(days=NO_QUALITY_DAYS)

        runs = sum(
            1 for a in data.activities if is_run_sport(a.sport) and activity_date(a) >= since
        )

        return no_quality(
            data.profile, days_since, runs, getattr(data.goal, "target_time", None),
        )

    @staticmethod
    def _adherence(data):

        from app.application.history.adherence_analyzer import AdherenceAnalyzer

        last_closed = data.today - timedelta(days=data.today.weekday() + 7)

        return AdherenceAnalyzer.analyze(
            CoachSanityAudit._plans(data), data.history, until_week=last_closed,
        )

    @staticmethod
    def _check_stalled(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        weekly, longest = AthleteDossier.closed_weeks(data)

        report = CoachSanityAudit._adherence(data)

        return stalled_plan(data.profile, weekly, longest, report.rate)

    @staticmethod
    def _check_adherence(data) -> Finding | None:

        report = CoachSanityAudit._adherence(data)

        weeks = report.weeks[-ADHERENCE_WEEKS:]

        return low_adherence(
            data.profile,
            sum(w.done for w in weeks),
            sum(w.planned for w in weeks),
            len(weeks),
        )

    @staticmethod
    def _check_stopped(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.application.history.weekly_buckets import activity_date
        from app.domain.value_objects.sports import is_run_sport

        runs = [activity_date(a) for a in data.activities if is_run_sport(a.sport)]

        days = (data.today - max(runs)).days if runs else None

        return stopped_running(
            data.profile, days, AthleteDossier._open_illness(data) is not None,
        )

    @staticmethod
    def snapshot(profile: str, today: date | None = None) -> Snapshot:
        """Os números de UM atleta pro painel: volume e maior treino das últimas 4 semanas
        fechadas, aderência e a próxima prova. Best-effort: o que faltar fica None."""

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.core.clock import today_local

        today = today or today_local()

        data = AthleteDossier._inputs(profile, None, None, None, today)

        km_week = long_km = adherence = next_race = None

        try:

            weekly, longest = AthleteDossier.closed_weeks(data)

            ran = [v for v in weekly[-4:] if v > 0]

            km_week = sum(ran) / len(ran) if ran else None

            long_km = max(longest[-4:] or [0.0]) or None

        except Exception as e:  # noqa: BLE001

            print(f"Sanidade: painel (volume) falhou p/ '{profile}': {e}")

        try:

            adherence = CoachSanityAudit._adherence(data).rate

        except Exception as e:  # noqa: BLE001

            print(f"Sanidade: painel (aderência) falhou p/ '{profile}': {e}")

        try:

            races = CoachSanityAudit._races_ahead(data)

            if races:

                weeks = (races[0]["date"] - today).days // 7

                next_race = f"{CoachSanityAudit._race_label(races[0])}, em {weeks} sem"

        except Exception as e:  # noqa: BLE001

            print(f"Sanidade: painel (prova) falhou p/ '{profile}': {e}")

        return Snapshot(profile, km_week, long_km, adherence, next_race)

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


def format_message(
    findings: list[Finding],
    names: dict[str, str] | None = None,
    audited: list[str] | None = None,
) -> str:
    """O aviso pro dono: um bloco por atleta, 🔴 alto antes de 🟡 atenção. Com `audited`, diz QUEM
    foi auditado e quem ficou sem achado novo — pra ninguém achar que só alguns são olhados."""

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

    if audited:

        quiet = [names.get(p, p) for p in audited if p not in by_profile]

        lines.append(f"Atletas auditados: {len(audited)}.")

        if quiet:

            lines.append(f"✅ Sem achado novo: {', '.join(quiet)}.")

        lines.append("")

    lines.append(
        "É só um aviso: nada foi alterado. O dossiê e o plano do atleta mostram o que o coach "
        "está vendo."
    )

    return "\n".join(lines)


def format_panel(
    snapshots: list[Snapshot],
    findings: list[Finding],
    names: dict[str, str] | None = None,
) -> str:
    """O painel de TODOS os atletas (segunda): um por linha, com o semáforo do que a auditoria viu
    e os números que o coach tem à mão. É a prova de que cada atleta foi olhado."""

    names = names or {}

    by_profile: dict[str, list[Finding]] = {}

    for finding in findings:

        by_profile.setdefault(finding.profile, []).append(finding)

    lines = [f"📋 Painel dos atletas — {len(snapshots)} auditados", ""]

    for snap in snapshots:

        items = by_profile.get(snap.profile, [])

        icon = "🔴" if any(f.level == HIGH for f in items) else ("🟡" if items else "🟢")

        bits = []

        if snap.km_week is not None:

            bits.append(f"~{snap.km_week:.0f} km/sem")

        if snap.long_km:

            bits.append(f"maior treino {snap.long_km:.0f} km")

        if snap.adherence is not None:

            bits.append(f"aderência {snap.adherence:.0%}")

        if snap.next_race:

            bits.append(snap.next_race)

        alerts = f" — {len(items)} alerta(s)" if items else ""

        lines.append(f"{icon} {names.get(snap.profile, snap.profile)}{alerts}: " + " · ".join(bits))

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


def run(
    send: bool,
    today: date | None = None,
    state: SanityState | None = None,
    force_panel: bool = False,
) -> str:
    """Audita TODOS os atletas ativos. Sem `send`: só mostra (dry-run, ignora o cooldown, mostra o
    painel). Com `send`: avisa o dono dos achados NOVOS (com a cobertura dos auditados) e, na
    segunda-feira (ou com `force_panel`), manda o painel de todos; grava quando avisou. Devolve o
    que foi enviado."""

    from app.core.clock import today_local

    today = today or today_local()

    state = state or SanityState()

    audited = CoachSanityAudit.athletes()

    findings = CoachSanityAudit.audit_all(today)

    stored = state.load()

    pending = fresh(findings, stored, today)

    names = {p: _name(p) for p in audited}

    def panel() -> str:

        snaps = [CoachSanityAudit.snapshot(p, today) for p in audited]

        return format_panel(snaps, findings, names)

    if not send:

        alert = format_message(findings, names, audited) if findings else "Sem achados."

        shown = f"{alert}\n\n{panel()}"

        print(shown)

        print(f"\n({len(pending)} de {len(findings)} seriam enviados agora — fora do cooldown)")

        return shown

    parts = []

    if pending:

        parts.append(format_message(pending, names, audited))

    if today.weekday() == 0 or force_panel:

        parts.append(panel())

    if not parts:

        print(f"{today} sanidade: sem achados novos ({len(findings)} em cooldown)")

        return ""

    message = "\n\n".join(parts)

    if asyncio.run(_send(message)):

        for finding in pending:

            stored[_key(finding)] = today.isoformat()

        state.save(stored)

        print(f"{today} sanidade: {len(pending)} achado(s) novo(s), painel={today.weekday() == 0}")

    return message


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--send", action="store_true")

    # manda o painel de todos os atletas hoje (por padrão só na segunda-feira)
    parser.add_argument("--painel", action="store_true")

    args = parser.parse_args()

    run(send=args.send, force_panel=args.painel)


if __name__ == "__main__":

    main()
