"""CONFERÊNCIA DA GERAÇÃO DO PLANO DE DOMINGO. Os checks são puros (recebem números): testados aqui
sem disco e sem IA. A ligação com os dados reais (`PlanGenerationMonitor.facts`) é testada com os
repositórios trocados por dublês — nenhum dado de atleta é lido."""

from contextlib import ExitStack
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.application.coach.context.athlete_dossier import AthleteDossier
from app.application.monitoring import plan_generation_monitor as monitor
from app.application.monitoring.plan_generation_monitor import (
    Facts,
    PlanGenerationMonitor,
    checks,
    cost_brl,
    cost_findings,
    cut_after_delivery,
    delivery,
    format_message,
    journal_findings,
    last_sunday,
    long_jump,
    network_plan,
    render_report,
    repeated_quality,
    repeated_sessions,
)
from app.application.planner.weekly_plan_notifier import PLAN_HOUR
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import INTERVAL, RECOVERY, REPEAT, WorkoutStep

BRT = ZoneInfo("America/Sao_Paulo")

SUNDAY = date(2026, 11, 8)

WEEK = date(2026, 11, 9)


def _facts(**changes) -> Facts:
    """Um domingo saudável do Renato: entregou 30,5 km, o plano novo pede 30,5 km, saiu às 20:01."""

    base = {
        "profile": "renato2",
        "name": "Renato",
        "sunday": SUNDAY,
        "week": WEEK,
        "since": datetime(2026, 11, 8, 3, 0, tzinfo=UTC),
        "due": True,
        "fresh": True,
        "plan_week": WEEK,
        "new_km": 30.5,
        "sessions": 3,
        "structured": 3,
        "longest_plan_km": 15.5,
        "sent": [datetime(2026, 11, 8, 20, 1, tzinfo=BRT)],
        "delivering": True,
        "last_planned_km": 30.5,
        "last_done_km": 30.5,
        "longest_recent_km": 15.5,
    }

    base.update(changes)

    return Facts(**base)


def _session(workout_type, km, steps=None, structure="") -> PlannedSession:

    return PlannedSession(
        day="thursday", workout_type=workout_type, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=None, target_pace_max=None,
        structure=structure, steps=steps or [],
    )


def _intervals(reps=4, meters=1000, pace=("5:25", "5:35")) -> list[WorkoutStep]:

    return [
        WorkoutStep(
            kind=REPEAT, reps=reps,
            steps=[
                WorkoutStep(
                    kind=INTERVAL, distance_m=meters, pace_min=pace[0], pace_max=pace[1],
                ),
                WorkoutStep(kind=RECOVERY, duration_sec=120),
            ],
        )
    ]


# --- apoio ---------------------------------------------------------------------------------------


def test_the_delivery_hour_is_the_one_the_notifier_uses():
    """Se alguém mudar a hora da entrega no notificador, o monitor tem que acompanhar."""

    assert monitor.DELIVERY_HOUR == PLAN_HOUR


def test_last_sunday_is_today_on_sunday_and_yesterday_after_midnight():

    night = datetime(2026, 11, 8, 22, 30, tzinfo=BRT)

    assert last_sunday(night) == datetime(2026, 11, 8, 0, 0, tzinfo=BRT)

    # Lisboa já virou a segunda: o domingo de referência é o de ontem
    lisbon = datetime(2026, 11, 9, 1, 30, tzinfo=ZoneInfo("Europe/Lisbon"))

    assert last_sunday(lisbon) == datetime(2026, 11, 8, 0, 0, tzinfo=ZoneInfo("Europe/Lisbon"))

    wednesday = datetime(2026, 11, 11, 9, 0, tzinfo=BRT)

    assert last_sunday(wednesday) == datetime(2026, 11, 8, 0, 0, tzinfo=BRT)


def test_cost_uses_the_list_price_of_the_model():

    pro = {"model": "gemini-3.1-pro-preview", "in": 100_000, "out": 10_000, "thoughts": 20_000}

    assert round(cost_brl(pro), 3) == 2.295

    # modelo desconhecido cai no preço padrão (o do flash)
    assert cost_brl({"model": "?", "in": 1_000_000}) == 0.15 * 5.40


# --- entrega -------------------------------------------------------------------------------------


def test_a_healthy_sunday_has_no_findings():

    assert checks(_facts()) == []


def test_a_missing_plan_is_high():

    found = delivery(_facts(plan_week=None))

    assert [(x.code, x.level) for x in found] == [("sem_plano", "alto")]

    assert "09/11" in found[0].text and "nenhum plano guardado" in found[0].text


def test_a_plan_of_another_week_is_high_and_says_which_week():

    found = delivery(_facts(plan_week=date(2026, 11, 2)))

    assert found[0].code == "sem_plano" and "02/11" in found[0].text


def test_a_generated_plan_with_no_message_sent_is_high():

    found = delivery(_facts(sent=[]))

    assert [(x.code, x.level) for x in found] == [("plano_nao_enviado", "alto")]


def test_a_late_message_is_watch():

    found = delivery(_facts(sent=[datetime(2026, 11, 8, 22, 10, tzinfo=BRT)]))

    assert [(x.code, x.level) for x in found] == [("entrega_atrasada", "atenção")]

    assert "22:10" in found[0].text and "130 min" in found[0].text


def test_a_message_within_the_margin_is_not_late():

    assert delivery(_facts(sent=[datetime(2026, 11, 8, 21, 29, tzinfo=BRT)])) == []


def test_before_the_check_hour_nothing_is_flagged():
    """Antes das 21h do fuso dele a geração pode estar rodando: não é falha."""

    assert delivery(_facts(due=False, plan_week=None, sent=[])) == []


def test_an_external_coach_athlete_is_not_checked():
    """Plano de treinador externo é o que o atleta manda, não a geração do coach."""

    assert checks(_facts(external=True, plan_week=None, sent=[], structured=0)) == []


def test_an_old_run_does_not_flag_a_missing_message():
    """O registro guarda só as últimas 10 mensagens: dias depois, a falta dela não prova nada."""

    assert delivery(_facts(fresh=False, sent=[])) == []


# --- plano de rede -------------------------------------------------------------------------------


def test_a_plan_with_no_coach_structure_is_the_network_plan():

    found = network_plan(_facts(structured=0))

    assert (found.code, found.level) == ("plano_de_rede", "alto")

    assert "Nenhuma das 3 sessões" in found.text


def test_a_plan_with_some_structure_missing_is_watch():

    found = network_plan(_facts(structured=2))

    assert found.level == "atenção" and "2 de 3" in found.text


def test_a_fully_structured_plan_is_fine():

    assert network_plan(_facts()) is None


# --- corte depois de entrega ---------------------------------------------------------------------


def test_cutting_the_volume_of_someone_who_delivered_is_high_with_the_numbers():
    """O caso do Renato em 08/11: entregou 30,5 km e o plano veio com 25 km de "descarga"."""

    found = cut_after_delivery(
        _facts(new_km=25.0, is_deload=True, deload_why="Semana de recuperação pelo sono baixo")
    )

    assert (found.code, found.level) == ("corte_apos_entrega", "alto")

    assert "30,5 km feitos de 30,5 km planejados" in found.text

    assert "25 km (-18% sobre 30,5 km)" in found.text

    assert "Semana de recuperação pelo sono baixo" in found.text


def test_a_cut_without_a_declared_deload_says_so():

    found = cut_after_delivery(_facts(new_km=25.0))

    assert found.level == "alto" and "Sem descarga declarada" in found.text


def test_a_small_dip_after_delivery_is_not_a_cut():

    assert cut_after_delivery(_facts(new_km=28.0)) is None


def test_someone_who_overshot_the_plan_and_got_the_plan_back_was_not_cut():
    """Mauricio, 08/11: planejou 37 km, fez 42,1 e recebeu 38 — a prescrição, não um corte."""

    assert cut_after_delivery(_facts(last_planned_km=37.0, last_done_km=42.1, new_km=38.0)) is None


def test_the_cut_is_measured_against_the_smaller_of_planned_and_done():

    found = cut_after_delivery(_facts(last_planned_km=30.0, last_done_km=27.5, new_km=24.0))

    assert found.level == "alto" and "-13% sobre 27,5 km" in found.text


def test_someone_who_did_not_deliver_can_be_cut():
    """Quem não entregou pode receber menos: aí o corte é leitura do que ele fez."""

    assert cut_after_delivery(_facts(new_km=20.0, delivering=False)) is None


def test_a_deload_flag_after_delivery_is_watch_even_without_a_big_cut():

    found = cut_after_delivery(_facts(new_km=29.5, is_deload=True))

    assert (found.code, found.level) == ("corte_apos_entrega", "atenção")

    assert "marcou a semana como descarga" in found.text


def test_no_comparison_without_the_numbers_of_the_week_before():

    assert cut_after_delivery(_facts(new_km=10.0, last_done_km=0.0)) is None


# --- maior treino --------------------------------------------------------------------------------


def test_a_small_step_in_the_longest_session_is_fine():

    assert long_jump(_facts(longest_plan_km=16.0, longest_recent_km=15.0)) is None


def test_a_big_step_in_the_longest_session_is_watch():

    found = long_jump(_facts(longest_plan_km=17.5, longest_recent_km=15.0))

    assert (found.code, found.level) == ("salto_do_maior_treino", "atenção")

    assert "17,5 km" in found.text and "17%" in found.text and "15 km" in found.text


# --- treino forte repetido -----------------------------------------------------------------------


def test_the_same_quality_session_two_weeks_in_a_row_is_found():

    new = [_session("Limiar", 8.0, steps=_intervals()), _session("Longão", 15.5)]

    old = [_session("Limiar", 8.0, steps=_intervals()), _session("Longão", 15.0)]

    assert repeated_sessions(new, old) == ["Limiar (8 km)"]


def test_a_different_series_or_pace_is_not_a_repeat():

    old = [_session("Limiar", 8.0, steps=_intervals())]

    assert repeated_sessions([_session("Limiar", 8.0, steps=_intervals(reps=5))], old) == []

    assert repeated_sessions(
        [_session("Limiar", 8.0, steps=_intervals(pace=("5:20", "5:30")))], old
    ) == []


def test_easy_runs_and_long_runs_repeating_do_not_count():

    new = [_session("Rodagem Base", 7.0, structure="7 km leves"), _session("Longão", 15.5)]

    old = [_session("Rodagem Base", 7.0, structure="7 km leves"), _session("Longão", 15.5)]

    assert repeated_sessions(new, old) == []


def test_without_steps_the_written_structure_is_compared():

    new = [_session("Ritmo de Prova", 7.0, structure="1 km leve\n4x 1000m a 5:25")]

    old = [_session("Ritmo de Prova", 7.0, structure="1 km leve\n4x 1000m a 5:25")]

    assert repeated_sessions(new, old) == ["Ritmo de Prova (7 km)"]


def test_sessions_with_nothing_to_compare_never_match():

    assert repeated_sessions([_session("Limiar", 8.0)], [_session("Limiar", 8.0)]) == []


def test_a_repeated_quality_session_is_watch():

    found = repeated_quality(_facts(repeated=["Limiar (8 km)"]))

    assert (found.code, found.level) == ("treino_forte_repetido", "atenção")

    assert "Limiar (8 km)" in found.text

    assert repeated_quality(_facts()) is None


# --- custo ---------------------------------------------------------------------------------------


def test_a_normal_sunday_cost_is_quiet():

    assert cost_findings({"renato2": 0.40, "fernanda": 0.35}, 2.3) == []


def test_an_expensive_plan_and_an_expensive_weekend_are_flagged():

    found = cost_findings({"renato2": 1.80, "fernanda": 0.35}, 6.0)

    assert [(x.profile, x.code) for x in found] == [
        ("renato2", "custo_alto"), ("geral", "custo_alto"),
    ]

    assert "R$ 1,80" in found[0].text and "R$ 6,00" in found[1].text


# --- journal -------------------------------------------------------------------------------------


def test_the_journal_markers_become_one_finding_per_athlete_and_kind():

    lines = [
        "tudo normal",
        "IA falhou no plano de 'joaosoares', fallback determinístico: 503",
        "IA falhou no plano de 'joaosoares', fallback determinístico: 503",
        "Falha ao enviar plano semanal para 'helio': timeout",
        "[governador] weekly_plan suprimido p/ 'mauricio': teto diário",
    ]

    found = journal_findings(lines)

    assert [(x.profile, x.code, x.level) for x in found] == [
        ("joaosoares", "ia_falhou", "alto"),
        ("helio", "envio_falhou", "alto"),
        ("mauricio", "envio_suprimido", "alto"),
    ]


def test_a_clean_journal_has_no_findings():

    assert journal_findings(["INFO: 200 OK", "plano gerado"]) == []


# --- textos --------------------------------------------------------------------------------------


def test_the_owner_message_says_all_is_well_when_it_is():

    facts = [_facts(), _facts(profile="fernanda", name="Fernanda", new_km=31.0)]

    text = format_message(facts, [], 2.26)

    assert "semana de 09/11" in text

    assert "2 de 2 atletas com o plano entregue" in text and "R$ 2,26" in text

    assert "Nenhum alerta: tudo certo" in text

    assert "🟢 Renato — 30,5 km · 3 treinos · enviado 20:01" in text

    assert "nada foi alterado" in text


def test_the_owner_message_lists_each_alert_with_title_numbers_and_what_to_do():

    facts = [_facts(new_km=25.0, is_deload=True, deload_why="sono baixo")]

    text = format_message(facts, checks(facts[0]), 2.0)

    assert "1 alerta(s): 1 sério(s) (🔴)" in text

    assert "🔴 Renato — 25 km" in text

    assert "Cortou o volume de quem entregou" in text

    assert "👉 Quem entrega absorve a carga" in text


def test_athletes_before_their_check_hour_are_listed_as_waiting():

    facts = [_facts(), _facts(profile="x", name="Ana", due=False, plan_week=None, sent=[])]

    text = format_message(facts, checks(facts[0]) + checks(facts[1]), 1.0)

    assert "1 de 1 atletas com o plano entregue" in text

    assert "🕐 Ainda não deu a hora no fuso de: Ana." in text


def test_the_screen_report_shows_numbers_alerts_and_the_text_the_athlete_got():

    f = _facts(
        new_km=25.0, is_deload=True, plan_cost_brl=0.37,
        text="🏃 Ritmind — Plano da semana\n\nBom domingo, Renato!",
    )

    report = render_report([f], checks(f), {"renato2": 0.37}, 2.26, [], texto=True)

    assert "semana de 09/11" in report and "domingo 08/11" in report

    assert "🔴 Renato — 25 km · 3 treinos · enviado 20:01" in report

    assert "estrutura do coach em 3/3 sessões · IA do plano R$ 0,37" in report

    assert "planejou 30,5 km, fez 30,5 km (entregou: sim)" in report

    assert "Cortou o volume de quem entregou" in report

    assert "como o atleta recebeu" in report and "Bom domingo, Renato!" in report

    assert "Journal do serviço: 0 marcador(es)" in report

    assert "RESUMO: 1 de 1 entregues · 1 alerta(s)." in report

    # sem --texto o texto do atleta não entra
    assert "Bom domingo" not in render_report([f], [], {}, 0.0, None)


def test_the_screen_report_says_when_the_journal_cannot_be_read():

    report = render_report([_facts()], [], {}, 0.0, None)

    assert "Journal do serviço: indisponível aqui" in report


def _run(send: bool, send_mock):

    with (
        patch.object(PlanGenerationMonitor, "athletes", return_value=["renato2"]),
        patch.object(PlanGenerationMonitor, "facts", return_value=_facts()),
        patch.object(PlanGenerationMonitor, "costs", return_value=({"renato2": 0.4}, 2.0)),
        patch.object(monitor, "read_journal", return_value=[]),
        patch.object(monitor, "_send", send_mock),
    ):

        return monitor.run(send=send, now=NOW)


def test_the_dry_run_shows_the_owner_message_and_sends_nothing(capsys):

    send = AsyncMock(return_value=True)

    message = _run(False, send)

    out = capsys.readouterr().out

    assert "RESUMO: 1 de 1 entregues · 0 alerta(s)." in out

    assert "o aviso que iria pro Telegram do dono" in out and "tudo certo" in out

    assert "Nenhum alerta: tudo certo" in message

    send.assert_not_called()


def test_with_send_the_owner_gets_exactly_the_message(capsys):

    send = AsyncMock(return_value=True)

    message = _run(True, send)

    send.assert_awaited_once_with(message)

    assert "aviso enviado (0 alerta(s))" in capsys.readouterr().out


# --- ligação com os dados reais (repositórios trocados por dublês) --------------------------------


def _plan(week=WEEK, sessions=None, **changes) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato Borges", objective="meia", phase="BASE", weekly_volume=30.5,
        running_days=["tuesday", "thursday", "sunday"], week_start=week,
        sessions=sessions if sessions is not None else [
            _session("Rodagem Base", 7.0, structure="7 km leves"),
            _session("Limiar", 8.0, steps=_intervals(), structure="4x 1 km"),
            _session("Longão", 15.5, structure="15,5 km"),
        ],
        **changes,
    )


def _outbox():

    plan_text = "🏃 Ritmind — Plano da semana\n\nBom domingo, Renato!"

    return [
        {"text": "🏃 Ritmind — Plano da semana (antigo)", "timestamp": "2026-11-01T23:00:00+00:00"},
        {"text": "Bom dia, Renato! Hoje é dia de treino", "timestamp": "2026-11-08T09:00:00+00:00"},
        {"text": plan_text, "timestamp": "2026-11-08T23:01:00+00:00"},
        {"text": plan_text + " (refeito)", "timestamp": "2026-11-09T00:48:00+00:00"},
    ]


def _patched(plan, history=None, runner=None, delivering=True):

    runner = runner or SimpleNamespace(
        name="Renato Borges", timezone="America/Sao_Paulo", external_coach=False, id="renato2",
    )

    data = SimpleNamespace(today=SUNDAY, target_week=None)

    ledger = [SimpleNamespace(in_progress=False, planned_km=30.5, done_km=30.0)]

    stack = ExitStack()

    stack.enter_context(
        patch("app.application.use_cases.load_runner_profile.LoadRunnerProfile.execute",
              return_value=runner)
    )
    stack.enter_context(
        patch("app.infrastructure.persistence.weekly_plan_repository.WeeklyPlanRepository.load",
              return_value=plan)
    )
    stack.enter_context(
        patch("app.infrastructure.persistence.weekly_plan_repository.WeeklyPlanRepository.history",
              return_value=history or [])
    )
    stack.enter_context(
        patch("app.infrastructure.persistence.coach_outbox_repository.CoachOutboxRepository.recent",
              return_value=_outbox())
    )
    stack.enter_context(patch.object(AthleteDossier, "_inputs", return_value=data))
    stack.enter_context(patch.object(AthleteDossier, "_is_delivering", return_value=delivering))
    stack.enter_context(patch.object(AthleteDossier, "_ledger", return_value=ledger))
    stack.enter_context(
        patch.object(AthleteDossier, "closed_weeks",
                     return_value=([28.0, 30.0], [14.0, 15.0, 15.5, 15.5]))
    )

    return stack


NOW = datetime(2026, 11, 9, 1, 30, tzinfo=UTC)  # domingo 22:30 em Brasília


def test_the_monitor_reads_what_was_sent_and_what_was_planned():

    with _patched(_plan()):

        f = PlanGenerationMonitor.facts("renato2", NOW)

    assert (f.sunday, f.week, f.plan_week) == (SUNDAY, WEEK, WEEK)

    assert f.due and f.fresh and not f.external

    assert f.name == "Renato"

    # só as mensagens de PLANO deste domingo; a última é a refeita
    assert [x.strftime("%d/%m %H:%M") for x in f.sent] == ["08/11 20:01", "08/11 21:48"]

    assert f.text.endswith("(refeito)")

    assert (f.sessions, f.structured, f.new_km, f.longest_plan_km) == (3, 3, 30.5, 15.5)

    assert f.delivering and (f.last_planned_km, f.last_done_km) == (30.5, 30.0)

    assert f.longest_recent_km == 15.5

    assert f.since == datetime(2026, 11, 8, 3, 0, tzinfo=UTC)

    assert checks(f) == []


def test_the_monitor_finds_a_quality_session_repeated_from_last_week():

    previous = _plan(week=WEEK - timedelta(days=7))

    with _patched(_plan(), history=[previous]):

        f = PlanGenerationMonitor.facts("renato2", NOW)

    assert f.repeated == ["Limiar (8 km)"]


def test_the_monitor_waits_for_the_check_hour_in_the_athlete_timezone():

    early = datetime(2026, 11, 8, 23, 30, tzinfo=UTC)  # 20:30 em Brasília

    with _patched(_plan()):

        f = PlanGenerationMonitor.facts("renato2", early)

    assert not f.due


def test_a_stored_plan_of_another_week_stops_the_reading_early():

    with _patched(_plan(week=date(2026, 11, 2))):

        f = PlanGenerationMonitor.facts("renato2", NOW)

    assert f.plan_week == date(2026, 11, 2) and f.sessions == 0 and f.sent == []

    assert [x.code for x in checks(f)] == ["sem_plano"]


def test_an_external_coach_athlete_is_read_but_never_flagged():

    runner = SimpleNamespace(
        name="Ana Souza", timezone="America/Sao_Paulo", external_coach=True, id="ana",
    )

    with _patched(None, runner=runner):

        f = PlanGenerationMonitor.facts("ana", NOW)

    assert f.external and checks(f) == []
