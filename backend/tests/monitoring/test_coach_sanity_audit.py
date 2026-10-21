"""AUDITORIA DE SANIDADE DO COACH (nº 77). O Leonardo ficou semanas com treino fraco e ninguém
soube: o treino do próprio coach lido como prova, esforço percebido ≤3/10 em 6 de 7 corridas, 0%
em zona forte e um pedido de "mais" sem resposta. A auditoria semanal só caça sintomas em
mensagens; esta olha o estado do coach contra os dados, todo dia, sem IA."""

from contextlib import ExitStack
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.history.athlete_asks_more import Ask
from app.application.history.goal_path import assess
from app.application.history.race_detector import RaceEvent
from app.application.monitoring import coach_sanity_audit as audit
from app.application.monitoring.coach_sanity_audit import (
    CoachSanityAudit,
    Finding,
    SanityState,
    Snapshot,
    asked_more_unanswered,
    easy_heavy,
    format_message,
    format_panel,
    fresh,
    low_adherence,
    low_effort,
    no_quality,
    path_gap,
    stagnant_form,
    stalled_plan,
    stopped_running,
    unbacked_race,
)

TODAY = date(2026, 10, 21)

MODULE = "app.application.monitoring.coach_sanity_audit"


# --- prova sem lastro ----------------------------------------------------------------------------


def _event(day=date(2026, 10, 9), weeks_ago=1, name="Ritmind · Ritmo de Prova 8.0km"):

    return RaceEvent(date=day, name=name, distance_km=8.0, weeks_ago=weeks_ago)


def test_a_race_nobody_registered_is_flagged_as_high():
    """O coach acha que houve prova (pós-prova: sem "puxar") sem prova na lista nem resultado."""

    finding = unbacked_race("leonardo", _event(), [], [date(2026, 12, 20)])

    assert finding.level == "alto" and finding.code == "prova_sem_lastro"
    assert "Ritmind · Ritmo de Prova 8.0km" in finding.text and "09/10" in finding.text
    assert "modo pós-prova" in finding.text


def test_a_race_with_a_result_or_a_list_entry_is_not_flagged():

    assert unbacked_race("renato2", _event(date(2026, 8, 23)), [date(2026, 8, 23)], []) is None

    # a lista do app com a data (±1 dia por fuso/virada)
    assert unbacked_race("x", _event(date(2026, 10, 9)), [], [date(2026, 10, 10)]) is None


def test_an_old_race_or_none_is_not_flagged():
    """Depois das 3 semanas de pós-prova o modo já acabou: não pesa mais."""

    assert unbacked_race("x", _event(weeks_ago=5), [], []) is None
    assert unbacked_race("x", None, [], []) is None


# --- esforço baixo o tempo todo ------------------------------------------------------------------


def test_low_effort_with_a_time_goal_close_to_the_race_is_flagged():
    """Leonardo: esforço ≤3/10 em 6 de 7, 0% em zona forte, prova em 8 semanas, meta 1h."""

    finding = low_effort(
        "leonardo", [2, 3, 2, 3, 4, 3, 3], 0, 8, "01:00:00", "a prova de 10 km",
    )

    assert finding.level == "atenção" and finding.code == "esforco_baixo"
    assert "≤3/10 em 6 de 7 corridas" in finding.text
    assert "0% do tempo em zona forte" in finding.text
    assert "em 8 semanas (meta 01:00:00)" in finding.text
    # é pra OLHAR: pode ser base de propósito
    assert "base de propósito" in finding.text


def test_low_effort_needs_every_condition():

    rpes = [2, 3, 2, 3, 3, 2]

    assert low_effort("x", rpes, 12, 8, "01:00:00", "a prova") is None        # tem tempo forte
    assert low_effort("x", rpes, None, 8, "01:00:00", "a prova") is None      # sem régua de FC
    assert low_effort("x", rpes, 0, 20, "01:00:00", "a prova") is None        # prova longe
    assert low_effort("x", rpes, 0, 2, "01:00:00", "a prova") is None         # taper
    assert low_effort("x", rpes, 0, 8, None, "a prova") is None               # sem meta de tempo
    assert low_effort("x", rpes, 0, None, "01:00:00", "a prova") is None      # sem prova datada
    assert low_effort("x", [2, 3, 2], 0, 8, "01:00:00", "a prova") is None    # poucos relatos
    assert low_effort("x", [2, 3, 7, 8, 6, 3], 0, 8, "01:00:00", "a prova") is None  # esforço real


# --- pediu mais e a dose não mudou ----------------------------------------------------------------

_ASKS = [Ask(date(2026, 10, 2), "treinos muito leve, poucas distâncias", "conversa")]

_FLAT = {"before_week": 12.0, "before_long": 10.0, "after_week": 13.0, "after_long": 9.0}


def test_a_request_for_more_that_changed_nothing_is_flagged_as_high():

    finding = asked_more_unanswered("leonardo", _ASKS, _FLAT, TODAY, body_tired=False)

    assert finding.level == "alto" and finding.code == "pediu_mais_sem_resposta"
    assert "Em 02/10 ele disse" in finding.text
    assert "há 19 dias, a dose não subiu" in finding.text
    assert "antes ~12 km/semana e maior treino 10.0 km" in finding.text
    assert "O corpo dele não justifica segurar" in finding.text


def test_the_request_is_fine_if_the_dose_rose_or_it_is_recent_or_the_body_says_no():

    rose = {**_FLAT, "after_week": 15.0}

    longer = {**_FLAT, "after_long": 12.0}

    recent = [Ask(date(2026, 10, 18), "q", "conversa")]

    assert asked_more_unanswered("x", _ASKS, rose, TODAY, False) is None
    assert asked_more_unanswered("x", _ASKS, longer, TODAY, False) is None
    # pediu há 3 dias: o coach ainda não teve uma semana pra responder
    assert asked_more_unanswered("x", recent, _FLAT, TODAY, False) is None
    # corpo sobrecarregado: segurar é a resposta certa
    assert asked_more_unanswered("x", _ASKS, _FLAT, TODAY, body_tired=True) is None
    assert asked_more_unanswered("x", [], _FLAT, TODAY, False) is None
    assert asked_more_unanswered("x", _ASKS, None, TODAY, False) is None


# --- rota abaixo da faixa ------------------------------------------------------------------------


def _path(weeks_left=8):

    return assess(
        distance_km=10.0, target_time="01:00:00", weeks_left=weeks_left,
        weekly_km=[14.2, 5.1, 0.0, 13.3, 10.0, 12.6, 10.2, 22.1],
        longest_km=[10.0, 5.1, 0.0, 8.3, 8.0, 7.5, 5.2, 9.0], runs_per_week=3, hard_pct=0,
    )


def test_a_route_below_the_reference_close_to_the_race_is_flagged():

    finding = path_gap("leonardo", _path(8))

    assert finding.code == "rota_abaixo_da_faixa" and finding.level == "atenção"
    assert "Faltam 8 semanas pra prova" in finding.text
    assert "faltam ~2 km no longão e ~9 km por semana" in finding.text
    assert "11-13 km" in finding.text and "28-38 km/semana" in finding.text


def test_the_route_is_not_flagged_when_far_or_covered_or_missing():

    assert path_gap("x", _path(12)) is None
    assert path_gap("x", None) is None

    covered = assess(
        distance_km=10.0, target_time="01:00:00", weeks_left=6,
        weekly_km=[26.0, 28.0, 30.0, 29.0, 31.0, 32.0, 30.0, 33.0],
        longest_km=[11.0, 12.0, 12.0, 11.0, 12.0, 13.0, 12.0, 13.0], runs_per_week=3,
    )

    assert path_gap("x", covered) is None


# --- forma estagnada ------------------------------------------------------------------


def test_a_form_stuck_for_weeks_close_to_the_race_is_flagged():

    finding = stagnant_form("leonardo", "STABLE", 6, 8)

    assert finding.code == "forma_estagnada"
    assert "estável há ~6 semanas" in finding.text and "prova em 8 semanas" in finding.text

    assert stagnant_form("x", "IMPROVING", 8, 8) is None
    assert stagnant_form("x", "STABLE", 4, 8) is None
    assert stagnant_form("x", "STABLE", 8, 20) is None
    assert stagnant_form("x", "STABLE", 8, None) is None


# --- cooldown, mensagem e envio ----------------------------------------------


def _f(profile="leonardo", code="esforco_baixo", level="atenção"):

    return Finding(profile, code, level, f"texto de {code}")


def test_a_finding_is_not_repeated_inside_the_cooldown():

    state = {"leonardo:esforco_baixo": "2026-10-18", "leonardo:forma_estagnada": "2026-10-10"}

    findings = [_f(), _f(code="forma_estagnada"), _f(code="rota_abaixo_da_faixa")]

    kept = fresh(findings, state, TODAY)

    assert [f.code for f in kept] == ["forma_estagnada", "rota_abaixo_da_faixa"]


def test_the_message_puts_high_first_groups_by_athlete_and_says_nothing_was_changed():

    text = format_message(
        [_f("mauricio"), _f("leonardo", "prova_sem_lastro", "alto"), _f("leonardo")],
        {"leonardo": "Leonardo", "mauricio": "Maurício"},
    )

    assert text.startswith("🔎 Auditoria de sanidade do coach — 3 achado(s) novo(s)")
    assert text.index("Leonardo") < text.index("Maurício")
    assert text.index("🔴 texto de prova_sem_lastro") < text.index("🟡 texto de esforco_baixo")
    assert "nada foi alterado" in text


AUDITED = ["fernanda", "leonardo", "mauricio"]


def _everyone(audited=AUDITED, findings=None):
    """Os 3 atletas auditados e o que a auditoria achou — sem tocar no storage da máquina."""

    stack = ExitStack()

    stack.enter_context(patch.object(CoachSanityAudit, "athletes", return_value=list(audited)))
    found = [_f()] if findings is None else findings

    stack.enter_context(patch.object(CoachSanityAudit, "audit_all", return_value=found))
    race = "a prova de 10 km em 20/12, em 8 sem"

    stack.enter_context(patch.object(
        CoachSanityAudit, "snapshot",
        side_effect=lambda p, today=None: Snapshot(p, 24.0, 11.0, 0.9, race),
    ))
    stack.enter_context(patch(f"{MODULE}._name", side_effect=lambda p: p.title()))

    return stack


def test_the_message_says_who_was_audited_and_who_had_nothing_new():
    """"Só recebi do Leonardo e do Maurício": a mensagem diz que TODOS foram auditados."""

    text = format_message(
        [_f("leonardo")], {"leonardo": "Leonardo", "fernanda": "Fernanda", "mauricio": "Maurício"},
        ["fernanda", "leonardo", "mauricio"],
    )

    assert "Atletas auditados: 3." in text
    assert "✅ Sem achado novo: Fernanda, Maurício." in text

    # sem a lista de auditados a mensagem segue como era
    assert "Atletas auditados" not in format_message([_f("leonardo")], {})


def test_the_weekly_panel_lists_every_athlete_with_a_traffic_light():

    snaps = [
        Snapshot("fernanda", 24.6, 11.5, 0.83, None),
        Snapshot("leonardo", 13.3, 9.0, 1.0, "a prova de 10 km em 20/12, em 8 sem"),
        Snapshot("helio", None, None, None, None),
    ]

    text = format_panel(
        snaps,
        [_f("leonardo", "prova_sem_lastro", "alto"), _f("leonardo")],
        {"fernanda": "Fernanda", "leonardo": "Leonardo", "helio": "Hélio"},
    )

    assert text.startswith("📋 Painel dos atletas — 3 auditados")
    assert "🟢 Fernanda: ~25 km/sem · maior treino 12 km · aderência 83%" in text
    assert "🔴 Leonardo — 2 alerta(s): ~13 km/sem · maior treino 9 km · aderência 100%" in text
    assert "🟢 Hélio: " in text

    yellow = format_panel(snaps[:1], [_f("fernanda")], {"fernanda": "Fernanda"})

    assert "🟡 Fernanda — 1 alerta(s)" in yellow


def test_a_dry_run_shows_everything_and_sends_nothing(tmp_path, capsys):

    state = SanityState(tmp_path / "state.json")

    with _everyone(), patch(f"{MODULE}._send", new=AsyncMock()) as send:

        shown = audit.run(send=False, today=TODAY, state=state)

    send.assert_not_called()
    assert "Leonardo" in shown and "texto de esforco_baixo" in capsys.readouterr().out
    assert "Atletas auditados: 3." in shown and "📋 Painel dos atletas — 3 auditados" in shown
    assert state.load() == {}


def test_sending_warns_once_then_stays_quiet_until_the_cooldown_ends(tmp_path):
    """Quarta 21/10, quinta 22/10 e quinta 29/10 (nenhuma é segunda: sem painel)."""

    state = SanityState(tmp_path / "state.json")

    with _everyone(), patch(f"{MODULE}._send", new=AsyncMock(return_value=True)) as send:

        first = audit.run(send=True, today=TODAY, state=state)
        second = audit.run(send=True, today=date(2026, 10, 22), state=state)
        later = audit.run(send=True, today=date(2026, 10, 29), state=state)

    assert "1 achado(s) novo(s)" in first and "Painel" not in first
    assert second == ""
    assert "1 achado(s) novo(s)" in later
    assert send.await_count == 2
    assert state.load() == {"leonardo:esforco_baixo": "2026-10-29"}


def test_on_monday_the_panel_of_everyone_goes_even_without_new_findings(tmp_path):
    """Segunda 26/10: o achado está em cooldown, mas o painel com TODOS os atletas sai."""

    state = SanityState(tmp_path / "state.json")

    state.save({"leonardo:esforco_baixo": "2026-10-23"})

    monday = date(2026, 10, 26)

    with _everyone(), patch(f"{MODULE}._send", new=AsyncMock(return_value=True)) as send:

        sent = audit.run(send=True, today=monday, state=state)

    assert send.await_count == 1
    assert sent.startswith("📋 Painel dos atletas — 3 auditados")
    assert "achado(s) novo(s)" not in sent
    assert "Fernanda" in sent and "Leonardo" in sent and "Mauricio" in sent


def test_on_monday_with_a_new_finding_the_alert_and_the_panel_go_together(tmp_path):

    state = SanityState(tmp_path / "state.json")

    with _everyone(), patch(f"{MODULE}._send", new=AsyncMock(return_value=True)) as send:

        sent = audit.run(send=True, today=date(2026, 10, 26), state=state)

    assert send.await_count == 1
    assert "1 achado(s) novo(s)" in sent and "📋 Painel dos atletas" in sent


def test_the_panel_can_be_forced_on_any_day(tmp_path):

    state = SanityState(tmp_path / "state.json")

    with _everyone(findings=[]), patch(f"{MODULE}._send", new=AsyncMock(return_value=True)) as send:

        sent = audit.run(send=True, today=TODAY, state=state, force_panel=True)

    assert send.await_count == 1 and sent.startswith("📋 Painel dos atletas — 3 auditados")


def test_an_unconfigured_owner_sends_nothing_and_does_not_burn_the_cooldown(tmp_path):

    state = SanityState(tmp_path / "state.json")

    with _everyone(), patch(f"{MODULE}._send", new=AsyncMock(return_value=False)):

        audit.run(send=True, today=TODAY, state=state)

    assert state.load() == {}


def test_no_findings_and_not_monday_no_message(tmp_path):

    state = SanityState(tmp_path / "s.json")

    with _everyone(findings=[]), patch(f"{MODULE}._send", new=AsyncMock()) as send:

        assert audit.run(send=True, today=TODAY, state=state) == ""

    send.assert_not_called()


# --- um check torto não derruba os outros ----------------------------------------------


def test_one_broken_check_does_not_stop_the_others():

    data = SimpleNamespace(profile="leonardo", today=TODAY)

    patches = [
        patch(
            "app.application.coach.context.athlete_dossier.AthleteDossier._inputs",
            return_value=data,
        ),
        patch.object(CoachSanityAudit, "_check_race", side_effect=RuntimeError("disco")),
        patch.object(CoachSanityAudit, "_check_effort", return_value=_f()),
        patch.object(CoachSanityAudit, "_check_asked_more", return_value=None),
        patch.object(CoachSanityAudit, "_check_path", return_value=None),
        patch.object(CoachSanityAudit, "_check_form", return_value=None),
        patch.object(CoachSanityAudit, "_check_easy_heavy", return_value=None),
        patch.object(CoachSanityAudit, "_check_no_quality", return_value=None),
        patch.object(CoachSanityAudit, "_check_stalled", return_value=None),
        patch.object(CoachSanityAudit, "_check_adherence", return_value=None),
        patch.object(CoachSanityAudit, "_check_stopped", return_value=None),
    ]

    for p in patches:

        p.start()

    try:

        found = CoachSanityAudit.audit("leonardo", TODAY)

    finally:

        for p in patches:

            p.stop()

    assert [f.code for f in found] == ["esforco_baixo"]


# --- checks que valem pra TODOS (não dependem de prova com data) -------------------------------


def test_too_much_easy_running_with_a_time_goal_is_flagged():
    """João (meta 5 km em 23 min): 11 das 20 sessões em 8 semanas eram rodagem leve."""

    finding = easy_heavy("joaosoares", 11, 20, "00:23:00")

    assert finding.code == "rodagem_demais" and finding.level == "atenção"
    assert "11 de 20 sessões prescritas" in finding.text and "(55%)" in finding.text
    assert "meta de tempo (00:23:00)" in finding.text

    assert easy_heavy("x", 11, 20, None) is None            # sem meta de tempo (saúde): ok
    assert easy_heavy("x", 5, 10, "00:50:00") is not None   # metade já pesa
    assert easy_heavy("x", 4, 10, "00:50:00") is None
    assert easy_heavy("x", 6, 7, "00:50:00") is None        # amostra pequena


def test_no_strong_stimulus_for_weeks_with_a_time_goal_is_flagged():

    finding = no_quality("joaosoares", 30, 7, "00:23:00")

    assert finding.code == "sem_estimulo_forte"
    assert "feito há 30 dias" in finding.text and "7 corridas nos últimos 21 dias" in finding.text

    assert "nas últimas 8 semanas" in no_quality("x", None, 8, "01:00:00").text

    assert no_quality("x", 10, 8, "01:00:00") is None    # fez forte há 10 dias
    assert no_quality("x", 30, 3, "01:00:00") is None    # quase não correu
    assert no_quality("x", 30, 8, None) is None          # sem meta de tempo


def test_a_plan_that_stopped_progressing_with_the_athlete_on_track_is_flagged():

    finding = stalled_plan("helio", [20.0, 21.0, 20.5, 20.0], [9.0, 9.5, 9.0, 9.0], 1.0)

    assert finding.code == "plano_parado"
    assert "~20 km/semana, variando só 5%" in finding.text and "~10 km" in finding.text
    assert "há 4 semanas com o plano em dia" in finding.text

    assert stalled_plan("x", [20.0, 26.0, 21.0, 20.0], [9.0] * 4, 1.0) is None     # volume mexeu
    assert stalled_plan("x", [20.0] * 4, [9.0, 11.0, 9.0, 9.0], 1.0) is None       # longão mexeu
    assert stalled_plan("x", [20.0] * 4, [9.0] * 4, 0.5) is None                   # não cumpre
    assert stalled_plan("x", [20.0, 0.0, 20.0, 20.0], [9.0] * 4, 1.0) is None      # semana parada
    assert stalled_plan("x", [20.0] * 3, [9.0] * 3, 1.0) is None                   # poucas semanas
    assert stalled_plan("x", [20.0] * 4, [9.0] * 4, None) is not None              # sem aderência


def test_low_adherence_means_the_plan_may_not_fit_his_routine():

    finding = low_adherence("joaosoares", 3, 9, 3)

    assert finding.code == "aderencia_baixa" and "Cumpriu 3 de 9 treinos" in finding.text
    assert "(33%)" in finding.text

    assert low_adherence("x", 6, 9, 3) is None       # 67%: ok
    assert low_adherence("x", 1, 4, 3) is None       # poucas sessões
    assert low_adherence("x", 1, 9, 2) is None       # poucas semanas


def test_an_athlete_who_stopped_running_without_illness_is_flagged_as_high():

    finding = stopped_running("helio", 16, False)

    assert finding.level == "alto" and finding.code == "parou_de_correr"
    assert "há 16 dias" in finding.text

    assert stopped_running("x", 16, True) is None     # doente: esperado
    assert stopped_running("x", 9, False) is None
    assert stopped_running("x", None, False) is None


def _race(day, km, target, role):

    return {"date": day.isoformat(), "distance_km": km, "target_time": target, "priority": role}


def test_every_upcoming_race_counts_not_only_the_main_one():
    """Renato2: o 15 km de 20/12 (B, 8 semanas) estava fora da conta porque só a meia (A, 23
    semanas) era olhada — fora de todas as janelas."""

    data = SimpleNamespace(
        today=TODAY, goal=None,
    )

    races = [
        _race(date(2027, 4, 4), 21.0975, "1:59:59", "A"),
        _race(date(2026, 12, 20), 15.0, "1:15:00", "B"),
        _race(date(2026, 9, 1), 10.0, "00:50:00", None),   # já passou
    ]

    dossier = "app.application.coach.context.athlete_dossier.AthleteDossier"

    with patch(f"{dossier}._races", return_value=races):

        ahead = CoachSanityAudit._races_ahead(data)

    assert [r["km"] for r in ahead] == [15.0, 21.0975]
    assert CoachSanityAudit._race_label(ahead[0]) == "a prova de 15 km em 20/12 (preparatória)"
    assert CoachSanityAudit._race_label(ahead[1]) == "a prova de 21.0975 km em 04/04 (principal)"


def test_low_effort_is_judged_against_the_nearest_race_even_if_it_is_preparatory():

    data = SimpleNamespace(profile="renato2", today=TODAY, goal=None)

    races = [
        _race(date(2027, 4, 4), 21.0975, "1:59:59", "A"),
        _race(date(2026, 12, 20), 15.0, "1:15:00", "B"),
    ]

    with patch(
        "app.application.coach.context.athlete_dossier.AthleteDossier._races", return_value=races,
    ), patch(
        "app.application.coach.context.athlete_dossier.AthleteDossier._hard_pct", return_value=0,
    ), patch.object(CoachSanityAudit, "_rpes", return_value=[2, 3, 2, 3, 3, 2]):

        finding = CoachSanityAudit._check_effort(data)

    assert finding is not None and finding.code == "esforco_baixo"
    assert "a prova de 15 km em 20/12 (preparatória) em 8 semanas (meta 1:15:00)" in finding.text
