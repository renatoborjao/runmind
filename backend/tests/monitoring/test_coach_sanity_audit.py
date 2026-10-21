"""AUDITORIA DE SANIDADE DO COACH (nº 77). O Leonardo ficou semanas com treino fraco e ninguém
soube: o treino do próprio coach lido como prova, esforço percebido ≤3/10 em 6 de 7 corridas, 0%
em zona forte e um pedido de "mais" sem resposta. A auditoria semanal só caça sintomas em
mensagens; esta olha o estado do coach contra os dados, todo dia, sem IA."""

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
    asked_more_unanswered,
    format_message,
    fresh,
    low_effort,
    path_gap,
    stagnant_form,
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


def test_a_dry_run_shows_everything_and_sends_nothing(tmp_path, capsys):

    state = SanityState(tmp_path / "state.json")

    with patch.object(CoachSanityAudit, "audit_all", return_value=[_f()]), patch(
        f"{MODULE}._send", new=AsyncMock()
    ) as send, patch(f"{MODULE}._name", side_effect=lambda p: p.title()):

        shown = audit.run(send=False, today=TODAY, state=state)

    send.assert_not_called()
    assert "Leonardo" in shown and "texto de esforco_baixo" in capsys.readouterr().out
    assert state.load() == {}


def test_sending_warns_once_then_stays_quiet_until_the_cooldown_ends(tmp_path):

    state = SanityState(tmp_path / "state.json")

    with patch.object(CoachSanityAudit, "audit_all", return_value=[_f()]), patch(
        f"{MODULE}._send", new=AsyncMock(return_value=True)
    ) as send, patch(f"{MODULE}._name", side_effect=lambda p: p.title()):

        first = audit.run(send=True, today=TODAY, state=state)
        second = audit.run(send=True, today=date(2026, 10, 22), state=state)
        later = audit.run(send=True, today=date(2026, 10, 29), state=state)

    assert "1 achado(s) novo(s)" in first and second == ""
    assert "1 achado(s) novo(s)" in later
    assert send.await_count == 2
    assert state.load() == {"leonardo:esforco_baixo": "2026-10-29"}


def test_an_unconfigured_owner_sends_nothing_and_does_not_burn_the_cooldown(tmp_path):

    state = SanityState(tmp_path / "state.json")

    with patch.object(CoachSanityAudit, "audit_all", return_value=[_f()]), patch(
        f"{MODULE}._send", new=AsyncMock(return_value=False)
    ), patch(f"{MODULE}._name", side_effect=lambda p: p):

        audit.run(send=True, today=TODAY, state=state)

    assert state.load() == {}


def test_no_findings_no_message(tmp_path):

    state = SanityState(tmp_path / "s.json")

    with patch.object(CoachSanityAudit, "audit_all", return_value=[]), patch(
        f"{MODULE}._send", new=AsyncMock()
    ) as send:

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
    ]

    for p in patches:

        p.start()

    try:

        found = CoachSanityAudit.audit("leonardo", TODAY)

    finally:

        for p in patches:

            p.stop()

    assert [f.code for f in found] == ["esforco_baixo"]
