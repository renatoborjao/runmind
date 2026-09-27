"""O DOSSIÊ do atleta — a base ÚNICA de todas as vozes do coach."""

from contextlib import ExitStack
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from app.application.coach.context.athlete_dossier import (
    BODY,
    PLAN_WEEK,
    AthleteDossier,
    _Inputs,
)
from app.domain.entities.daily_checkin import DailyCheckin
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.session_rpe import SessionRpe
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.context.athlete_dossier"

TODAY = date(2026, 9, 27)


def _data(**overrides) -> _Inputs:

    data = _Inputs(profile="renato", today=TODAY)

    data.runner = make_runner()

    data.history = TrainingHistory(activities=[])

    data.goal = TrainingGoal(
        name="15 km sub 1h20", distance_km=15.0,
        target_time="01:20:00", race_date=date(2026, 12, 20),
    )

    for key, value in overrides.items():

        setattr(data, key, value)

    return data


def _plan(sessions, week_start, source="runmind") -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="15k", phase="BUILD",
        weekly_volume=30.0, running_days=["Tuesday"],
        week_start=week_start, sessions=sessions, source=source,
    )


def _session(day, kind="Rodagem"):

    return PlannedSession(
        day=day, workout_type=kind, objective="Base",
        planned_distance_km=6.0, planned_duration_minutes=None,
        target_pace_min=None, target_pace_max=None,
    )


# ---- render -----------------------------------------------------------------


def test_render_has_header_titles_and_respects_exclude():

    sections = {
        name: [f"linha-{name}"]
        for name in (
            "who", "capacity", "evolution", "body", "perception", "patterns",
            "plan_week", "coach_mind",
        )
    }

    with ExitStack() as stack:

        stack.enter_context(
            patch.object(AthleteDossier, "_inputs", return_value=_data())
        )

        for name, lines in sections.items():

            stack.enter_context(
                patch.object(AthleteDossier, f"_{name}", return_value=lines)
            )

        full = AthleteDossier.render("renato")

        partial = AthleteDossier.render("renato", exclude=(PLAN_WEEK, BODY))

    assert full.startswith("DOSSIÊ DO ATLETA")
    assert "27/09/2026" in full
    assert "▸ CORPO" in full and "linha-body" in full
    assert "▸ PERCEPÇÃO" in full
    assert "linha-plan_week" not in partial and "linha-body" not in partial
    assert "linha-perception" in partial


def test_failing_section_is_skipped_not_fatal():

    with (
        patch.object(AthleteDossier, "_inputs", return_value=_data()),
        patch.object(AthleteDossier, "_who", return_value=["quem"]),
        patch.object(AthleteDossier, "_capacity", side_effect=Exception("boom")),
        patch.object(AthleteDossier, "_evolution", return_value=[]),
        patch.object(AthleteDossier, "_body", return_value=[]),
        patch.object(AthleteDossier, "_perception", return_value=[]),
        patch.object(AthleteDossier, "_patterns", return_value=[""]),
        patch.object(AthleteDossier, "_plan_week", return_value=[]),
        patch.object(AthleteDossier, "_coach_mind", return_value=[]),
    ):

        out = AthleteDossier.render("renato")

    assert "quem" in out
    assert "CAPACIDADE" not in out
    # seção só com linha vazia não vira título solto
    assert "PADRÕES" not in out


def test_render_is_empty_when_the_base_fails():

    with patch.object(AthleteDossier, "_inputs", side_effect=Exception("boom")):

        assert AthleteDossier.render("renato") == ""


# ---- quem é -----------------------------------------------------------------


def test_who_counts_days_to_the_race_and_lists_injuries():

    data = _data()

    data.runner.injuries = ["canelite"]

    with patch(
        "app.application.races.race_intel_service.RaceIntelService"
    ) as intel:

        intel.render_context.return_value = "DOSSIÊ DA PROVA: plana, largada 7h"

        lines = AthleteDossier._who(data)

    text = "\n".join(lines)

    assert "Prova-âncora" in text and "faltam 84 dias" in text
    assert "DOSSIÊ DA PROVA" in text
    assert "canelite" in text


def test_past_race_is_not_treated_as_the_target():
    """Prova vencida não é alvo: o coach seguia 'periodizando' pra ela."""

    data = _data(goal=TrainingGoal(
        name="10k", distance_km=10.0, target_time=None,
        race_date=date(2026, 8, 23),
    ))

    text = "\n".join(AthleteDossier._who(data))

    assert "JÁ PASSOU" in text
    assert "faltam" not in text
    assert "Prova-âncora" not in text


def test_external_coach_is_flagged():

    data = _data()

    data.runner.external_coach = True

    assert "TREINADOR EXTERNO" in "\n".join(AthleteDossier._who(data))


# ---- plano da semana --------------------------------------------------------


def test_plan_week_flags_an_ended_week():

    data = _data(plan=_plan(
        [_session("Tuesday")], week_start=date(2026, 9, 7), source="externo",
    ))

    text = "\n".join(AthleteDossier._plan_week(data))

    assert "JÁ ENCERRADA" in text
    assert "aguardando o plano desta semana" in text


def test_plan_week_keeps_current_week_when_all_sessions_are_past():
    """Domingo, atleta de ter/qui/sáb: a semana está VIGENTE mesmo com tudo
    atrás — negar o plano seria mentira."""

    data = _data(plan=_plan(
        [_session("Tuesday"), _session("Thursday"), _session("Saturday")],
        week_start=date(2026, 9, 21),
    ))

    text = "\n".join(AthleteDossier._plan_week(data))

    assert "JÁ ENCERRADA" not in text
    assert "Semana de 21/09 — fase BUILD" in text


def test_plan_week_without_plan():

    assert AthleteDossier._plan_week(_data(plan=None)) == [
        "Sem plano da semana registrado."
    ]


# ---- percepção --------------------------------------------------------------


def _rpe(day, rpe, **kw):

    return SessionRpe(
        activity_id=hash(day) % 1000, day=day, duration_min=50.0, rpe=rpe,
        srpe=50.0 * rpe, at=f"{day}T20:00:00", **kw,
    )


def test_perception_shows_rpe_feel_source_and_checkins():

    rpe_repo = MagicMock()
    rpe_repo.return_value.load_sessions.return_value = [
        _rpe("2026-09-26", 7, feel="sentiu-se cansado", source="relógio"),
        _rpe("2026-09-24", 5, note="perna pesada", source="conversa"),
        _rpe("2026-08-01", 9),  # fora da janela
    ]

    checkins = MagicMock()
    checkins.return_value.load.return_value = [
        DailyCheckin(
            day="2026-09-25", at="2026-09-25T08:00:00", energy=2,
            soreness=3, note="panturrilha",
        ),
    ]

    with (
        patch(
            "app.infrastructure.persistence.session_rpe_repository."
            "SessionRpeRepository", rpe_repo,
        ),
        patch(
            "app.infrastructure.persistence.checkin_repository."
            "CheckinRepository", checkins,
        ),
        patch(
            "app.application.coach.intelligence.checkin_service."
            "CheckinService.render_recent", return_value="",
        ),
        patch(
            "app.application.coach.conversation.rpe_flow.RpeFlow.recent_note",
            return_value="",
        ),
    ):

        text = "\n".join(AthleteDossier._perception(_data()))

    assert "esforço percebido 7/10, sensação sentiu-se cansado (relógio)" in text
    assert '"perna pesada" (conversa)' in text
    assert "01/08" not in text
    assert "energia 2/5" in text and "dor nível 3" in text
    assert "panturrilha" in text


def test_perception_nudges_the_coach_when_blind():
    """Sem relato nenhum, o coach SABE que está cego (e pode perguntar)."""

    empty = MagicMock()
    empty.return_value.load_sessions.return_value = []
    empty.return_value.load.return_value = []

    with (
        patch(
            "app.infrastructure.persistence.session_rpe_repository."
            "SessionRpeRepository", empty,
        ),
        patch(
            "app.infrastructure.persistence.checkin_repository."
            "CheckinRepository", empty,
        ),
    ):

        lines = AthleteDossier._perception(_data())

    assert "Sem relato de esforço" in lines[0]


# ---- o que o coach já sabe/disse --------------------------------------------


def test_recent_coach_messages_keep_last_week_and_drop_old():

    outbox = MagicMock()
    outbox.return_value.recent.return_value = [
        {"text": "análise velha", "timestamp": "2026-09-01T10:00:00"},
        {"text": "Bom dia! Hoje segura o leve em 154.",
         "timestamp": "2026-09-26T07:00:00"},
        {"text": "x" * 900, "timestamp": "2026-09-27T09:00:00"},
    ]

    with patch(
        "app.infrastructure.persistence.coach_outbox_repository."
        "CoachOutboxRepository", outbox,
    ):

        text = AthleteDossier._recent_coach_messages(_data())

    assert "análise velha" not in text
    assert "26/09: Bom dia! Hoje segura o leve em 154." in text
    assert "…" in text  # longa demais: truncada
    assert "não contradiga" in text


def test_coach_mind_brings_memory_learnings_attention_and_summary():

    conv = MagicMock()
    conv.return_value.load_summary.return_value = {"summary": "falaram do 15k"}

    with (
        patch(
            "app.application.coach.memory.runner_memory_service."
            "RunnerMemoryService"
        ) as memory,
        patch("app.core.config.get_settings") as settings,
        patch(
            "app.application.coach.memory.coach_learning_service."
            "CoachLearningService"
        ) as learnings,
        patch(
            "app.infrastructure.persistence.coach_attention_log."
            "CoachAttentionLog"
        ) as attention,
        patch.object(AthleteDossier, "_recent_coach_messages", return_value=""),
        patch(
            "app.infrastructure.persistence.conversation_repository."
            "ConversationRepository", conv,
        ),
    ):

        memory.render.return_value = "Memória: prefere longão no domingo"
        memory.motivation_anchor.return_value = "Corre pela filha"
        settings.return_value.coach_learning_inject_enabled = True
        learnings.render.return_value = "Aprendi: segura bem 30 km"
        attention.render.return_value = "Já cobrou: leve acima do teto"

        text = "\n".join(AthleteDossier._coach_mind(_data()))

    for piece in (
        "longão no domingo", "Corre pela filha", "segura bem 30 km",
        "leve acima do teto", "Resumo das conversas com ele: falaram do 15k",
    ):
        assert piece in text


# ---- evolução / corpo -------------------------------------------------------


def test_evolution_includes_lifetime_stats():

    archive = MagicMock()
    archive.return_value.stats.return_value = {
        "total_runs": 123, "total_km": 861.4,
        "first_date": "2025-03-14", "longest_km": 21.1,
    }

    with (
        patch(
            "app.infrastructure.persistence.activity_archive_repository."
            "ActivityArchiveRepository", archive,
        ),
        patch(
            "app.application.history.weekly_evolution_digest."
            "WeeklyEvolutionDigest.for_profile", return_value="",
        ),
    ):

        text = "\n".join(
            line for line in AthleteDossier._evolution(_data()) if line
        )

    assert "Histórico geral registrado: 123 treinos, 861 km desde 03/2025" in text


def _reading(state="RECOVERY_FLAG"):

    reading = MagicMock(body_state=state, limiter="sono")

    reading.load.acwr = 1.12

    return reading


def test_body_state_line_and_sleep_but_no_sleep_verdict_when_worsening():
    """Piora REAL da recuperação: o veredito 'o sono não pesa na execução'
    contradiria a leitura — fica de fora."""

    drift = MagicMock(worsening=True)

    data = _data(reading=_reading(), drift=drift)

    with (
        patch(
            "app.application.coach.planning.body_directive.body_plan_directive",
            return_value="STATUS DO CORPO — PIORA REAL",
        ),
        patch(
            "app.application.coach.intelligence.sleep_reading_service."
            "SleepReadingService"
        ) as sleep,
        patch(
            "app.application.history.sleep_performance_analyzer."
            "sleep_performance_directive",
            return_value="SONO×EXECUÇÃO",
        ) as sleep_verdict,
        patch(
            "app.application.history.injury_risk_analyzer.InjuryRiskAnalyzer"
        ),
        patch(
            "app.application.history.injury_risk_analyzer.injury_risk_directive",
            return_value="",
        ),
        patch.object(AthleteDossier, "_prehab", return_value=""),
        patch(
            "app.application.history.deload_analyzer.deload_directive",
            return_value="SINAL DE DESCARGA",
        ),
        patch(
            "app.application.history.deload_analyzer.DeloadAnalyzer"
        ),
        patch(
            "app.application.coach.planning.ai_plan_service.AIPlanService."
            "_weeks_since_race", return_value=None,
        ),
    ):

        sleep.read.return_value = MagicMock(
            has_data=True, avg_hours=6.3, direction="falling", debt=True,
        )

        text = "\n".join(line for line in AthleteDossier._body(data) if line)

    assert "Estado: recuperação em queda; limitador: sono; " in text
    assert "(ACWR) 1.12" in text
    assert "PIORA REAL" in text
    assert "Sono: ~6.3h/noite, caindo (abaixo do que o corpo pede)." in text
    assert "SINAL DE DESCARGA" in text
    assert "SONO×EXECUÇÃO" not in text
    sleep_verdict.assert_not_called()


def test_archive_history_dedups_and_keeps_only_runs_newest_first():

    from tests.coach.factories import make_activity

    run_old = make_activity(id=1, start_date=datetime(2026, 9, 1, 7))
    run_new = make_activity(id=2, start_date=datetime(2026, 9, 20, 7))
    swim = make_activity(id=3, sport="Swim", start_date=datetime(2026, 9, 21, 7))

    history = AthleteDossier._archive_history([run_old, swim, run_new])

    assert [a.id for a in history.activities] == [2, 1]


def test_coach_voice_only_drops_the_data_sheet_and_keeps_the_opinion():
    """A mensagem enviada tem ficha de números + a fala do coach; o corte cru
    pegava só a ficha e a opinião sumia (dossiê 27/09)."""

    sent = (
        "🏃 Ritmind\n\nMauricio, foi uma rodagem extra, mas a FC ficou salgada no Z3."
        "\n\n✅ Executado\n• domingo (27/09)\n• Distância: 8.51 km\n• FC média: 136"
        "\n\n📊 Análise\n• 61% do tempo na Zona 3 tira a característica de leve."
        "\n\n⚠️ Ponto de atenção\n• Treino extra em Z3 cobra conta nos 15 km."
        "\n\n➡️ Na terça, segure a FC abaixo de 136."
        "\n\n👟 Contei essa no teu Novablast."
    )

    voice = AthleteDossier._coach_voice_only(sent)

    assert voice.startswith("Mauricio, foi uma rodagem extra")
    assert "61% do tempo na Zona 3" in voice
    assert "cobra conta nos 15 km" in voice
    assert "segure a FC abaixo de 136" in voice
    assert "Distância" not in voice and "Novablast" not in voice


def test_coach_voice_only_falls_back_to_raw_when_all_is_sheet():

    assert AthleteDossier._coach_voice_only(
        "🏃 Ritmind\n\n✅ Executado\n• 8 km"
    ).startswith("🏃 Ritmind")
