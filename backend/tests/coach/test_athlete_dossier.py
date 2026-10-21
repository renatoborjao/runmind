"""O DOSSIÊ do atleta — a base ÚNICA de todas as vozes do coach."""

from contextlib import ExitStack
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

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

RACES = "app.application.races.race_service.RaceService.list"


@pytest.fixture(autouse=True)
def _no_race_list_by_default():
    """O dossiê lê a lista de provas do disco (e a reconcilia com o perfil): nos
    testes, por padrão, atleta sem lista — nada de tocar no storage real."""

    with patch(RACES, return_value=[]):

        yield

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
            return_value="SINAL DE DESCARGA (plano)",
        ),
        patch(
            "app.application.history.deload_analyzer.deload_chat_line",
            return_value="SINAL DE DESCARGA (chat)",
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
    # voz que NÃO monta o plano (sem semana-alvo): o fato curto, nunca a instrução
    assert "SINAL DE DESCARGA (chat)" in text
    assert "SINAL DE DESCARGA (plano)" not in text
    assert "SONO×EXECUÇÃO" not in text
    sleep_verdict.assert_not_called()


def test_only_the_plan_voice_gets_the_deload_instruction():
    """O plano passa a semana-alvo (target_week): só ele recebe a instrução completa;
    chat, análise, resumos e nutrição leem a mesma base com o fato curto."""

    for target_week, expected, absent in (
        (date(2026, 10, 26), "SINAL DE DESCARGA (plano)", "SINAL DE DESCARGA (chat)"),
        (None, "SINAL DE DESCARGA (chat)", "SINAL DE DESCARGA (plano)"),
    ):

        data = _data(reading=_reading(), drift=None)

        data.target_week = target_week

        with (
            patch(
                "app.application.coach.planning.body_directive.body_plan_directive",
                return_value="",
            ),
            patch(
                "app.application.coach.intelligence.sleep_reading_service."
                "SleepReadingService"
            ) as sleep,
            patch(
                "app.application.history.sleep_performance_analyzer."
                "sleep_performance_directive",
                return_value="",
            ),
            patch("app.application.history.injury_risk_analyzer.InjuryRiskAnalyzer"),
            patch(
                "app.application.history.injury_risk_analyzer.injury_risk_directive",
                return_value="",
            ),
            patch.object(AthleteDossier, "_prehab", return_value=""),
            patch.object(AthleteDossier, "_push_room", return_value=""),
            patch(
                "app.application.history.deload_analyzer.deload_directive",
                return_value="SINAL DE DESCARGA (plano)",
            ),
            patch(
                "app.application.history.deload_analyzer.deload_chat_line",
                return_value="SINAL DE DESCARGA (chat)",
            ),
            patch("app.application.history.deload_analyzer.DeloadAnalyzer"),
            patch(
                "app.application.coach.planning.ai_plan_service.AIPlanService."
                "_weeks_since_race", return_value=None,
            ),
        ):

            sleep.read.return_value = MagicMock(has_data=False)

            text = "\n".join(line for line in AthleteDossier._body(data) if line)

        assert expected in text
        assert absent not in text


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


# ---- calendário de provas (papel e distância) --------------------------------


def _race(name, when, km, priority=None, suggested=None, target="1:15:00"):

    return {
        "id": name, "name": name, "date": when, "distance_km": km,
        "target_time": target, "priority": priority,
        "priority_suggested": suggested,
        "priority_effective": priority or suggested, "past": False,
    }


def test_who_shows_the_whole_race_calendar_with_roles():
    """Renato: 15 km (dez) preparatória + meia (abr) principal. O dossiê lista as
    duas com papel, e a mais próxima deixa de ser 'periodize pra ela'."""

    data = _data()

    races = [
        _race("Villa-Lobos (15 km)", "2026-12-20", 15.0, suggested="B"),
        _race("Meia Maratona SP", "2027-04-04", 21.0975, suggested="A",
              target="1:59:59"),
    ]

    with patch(RACES, return_value=races), patch(
        "app.application.races.race_intel_service.RaceIntelService"
    ) as intel:

        intel.render_context.return_value = ""

        text = "\n".join(AthleteDossier._who(data))

    assert "CALENDÁRIO DE PROVAS" in text
    assert "Villa-Lobos (15 km)" in text and "PREPARATÓRIA (B), sugerido" in text
    assert "Meia Maratona SP" in text and "PRINCIPAL (A), sugerido" in text
    assert "Próxima prova:" in text
    # a âncora deixa de mandar "periodize pra ela" (ela é só preparatória)
    assert "periodize pra ela" not in text
    # a hierarquia por texto não duplica o recado
    assert "HIERARQUIA DE PROVAS" not in text


def test_who_keeps_the_anchor_wording_with_a_single_race():
    """Uma prova só (sem papel B/C escolhido): nada muda — âncora e hierarquia."""

    data = _data()

    with patch(
        RACES, return_value=[_race("15 km", "2026-12-20", 15.0, suggested="A")]
    ), patch(
        "app.application.races.race_intel_service.RaceIntelService"
    ) as intel:

        intel.render_context.return_value = ""

        text = "\n".join(AthleteDossier._who(data))

    assert "CALENDÁRIO DE PROVAS" not in text
    assert "Prova-âncora (periodize pra ela)" in text


def test_who_shows_the_list_name_of_a_single_race():
    """O atleta vê o nome da lista na aba Treino; com uma prova só o coach não o enxergava."""

    data = _data()

    with patch(
        RACES, return_value=[_race("Corrida 10km/15km", "2026-12-20", 10.0)]
    ), patch(
        "app.application.races.race_intel_service.RaceIntelService"
    ) as intel:

        intel.render_context.return_value = ""

        text = "\n".join(AthleteDossier._who(data))

    assert "PROVA NA LISTA DO APP" in text and "Corrida 10km/15km" in text
    # e o resto do dossiê segue como estava
    assert "Prova-âncora (periodize pra ela)" in text


def test_who_does_not_repeat_the_list_name_when_the_calendar_lists_the_races():

    data = _data()

    races = [
        _race("Villa-Lobos (15 km)", "2026-12-20", 15.0, suggested="B"),
        _race("Meia Maratona SP", "2027-04-04", 21.0975, suggested="A"),
    ]

    with patch(RACES, return_value=races), patch(
        "app.application.races.race_intel_service.RaceIntelService"
    ) as intel:

        intel.render_context.return_value = ""

        text = "\n".join(AthleteDossier._who(data))

    assert "PROVA NA LISTA DO APP" not in text


def test_who_survives_a_calendar_failure():
    """Falha lendo a lista de provas nunca derruba o dossiê."""

    data = _data()

    with patch(RACES, side_effect=RuntimeError("disco")), patch(
        "app.application.races.race_intel_service.RaceIntelService"
    ) as intel:

        intel.render_context.return_value = ""

        text = "\n".join(AthleteDossier._who(data))

    assert "Prova-âncora (periodize pra ela)" in text


def test_taper_zone_follows_the_role_of_the_next_race_in_the_dossier():
    """Renato: o 15 km (preparatória) é a próxima — a zona de taper da descarga
    vira o mini-polimento (1 semana), não a de prova principal."""

    data = _data()

    races = [
        _race("Villa-Lobos (15 km)", "2026-12-20", 15.0, suggested="B"),
        _race("Meia Maratona SP", "2027-04-04", 21.0975, suggested="A"),
    ]

    with patch(RACES, return_value=races):

        assert AthleteDossier._taper_zone(data) == 1

    # uma prova só: padrão (None)
    with patch(RACES, return_value=[_race("15 km", "2026-12-20", 15.0, suggested="A")]):

        assert AthleteDossier._taper_zone(_data()) is None


# ---- rota até a meta e pedido de mais carga (nº 76) --------------------------------------------


def _weekly_runs(*km_by_week, first_monday=date(2026, 8, 31)):
    """Uma corrida por semana (segunda), `km_by_week` da mais antiga pra mais recente."""

    from datetime import timedelta

    from tests.coach.factories import make_activity

    return [
        make_activity(
            id=i, distance=km * 1000,
            start_date=datetime.combine(first_monday + timedelta(weeks=i), datetime.min.time()),
        )
        for i, km in enumerate(km_by_week)
        if km
    ]


def test_the_route_shows_the_gap_to_the_goal_in_the_plan_voice_and_a_short_fact_elsewhere():
    """Leonardo: 10 km em 1h a 8 semanas, longão parado e ~13 km por semana."""

    acts = _weekly_runs(0, 8.3, 10.0, 7.5, 5.2, 9.0, 8.0, 6.0, 0)

    goal = TrainingGoal(
        name="10 km sub 1h", distance_km=10.0, target_time="01:00:00",
        race_date=date(2026, 12, 20),
    )

    base = dict(
        activities=acts, goal=goal, runner=make_runner(weekly_training_days=3),
        today=date(2026, 10, 21),
    )

    plan = AthleteDossier._route(_data(target_week=date(2026, 10, 26), **base))

    assert len(plan) == 1 and plan[0].startswith("ROTA ATÉ A META")
    assert "faltam 7 semanas pra 10 km em 01:00:00" in plan[0]
    assert "FALTAM" in plan[0] and "o primeiro JÁ nesta semana" in plan[0]

    chat = AthleteDossier._route(_data(**base))

    assert len(chat) == 1 and chat[0].startswith("Rota até a meta (hipótese de treinador")
    assert "FALTAM" not in chat[0]


def test_the_route_aims_at_the_main_race_not_the_nearest_preparatory_one():
    """Renato: o 15 km de dezembro é preparatória (B); a rota mira a meia (A) de abril."""

    acts = _weekly_runs(25, 28, 30, 27, 29, 31, 28, 30, 0)

    races = [
        _race("Villa-Lobos (15 km)", "2026-12-20", 15.0, suggested="B"),
        _race("Meia Maratona SP", "2027-04-04", 21.0975, suggested="A", target="1:59:59"),
    ]

    with patch(RACES, return_value=races):

        text = AthleteDossier._route(
            _data(target_week=date(2026, 10, 26), activities=acts, today=date(2026, 10, 21))
        )[0]

    assert "pra 21,1 km em 1:59:59" in text
    assert "faltam 22 semanas" in text
    assert "~18-21 km" in text


def test_no_route_without_a_dated_race():

    goal = TrainingGoal(name="saúde", distance_km=5.0, target_time=None, race_date=None)

    assert AthleteDossier._route(_data(goal=goal, activities=_weekly_runs(10, 12, 11))) == []


_ASK_TURNS = [
    {"role": "user", "timestamp": "2026-10-02T15:51:00-03:00",
     "text": "venho achando as metas muito baixas, os treinos muito leve, poucas distâncias"},
    {"role": "assistant", "timestamp": "2026-10-02T15:52:00-03:00", "text": "Entendi!"},
]


def _patch_asks(turns=None, checkins=None):

    stack = ExitStack()

    stack.enter_context(patch(
        "app.infrastructure.persistence.conversation_repository.ConversationRepository.load",
        return_value=_ASK_TURNS if turns is None else turns,
    ))
    stack.enter_context(patch(
        "app.infrastructure.persistence.checkin_repository.CheckinRepository.load",
        return_value=[] if checkins is None else checkins,
    ))
    stack.enter_context(patch(f"{MODULE}.AthleteDossier._hard_pct", return_value=0))

    return stack


def test_his_request_for_more_reaches_the_plan_as_a_directive_and_the_chat_as_a_fact():

    reading = MagicMock(body_state="BALANCED")

    base = dict(today=date(2026, 10, 21), activities=_weekly_runs(0, 8.3, 10.0, 7.5, 5.2, 9.0, 8.0))

    with _patch_asks():

        plan = AthleteDossier._asks_more(
            _data(target_week=date(2026, 10, 26), reading=reading, **base), [2, 3, 2, 3],
        )

        chat = AthleteDossier._asks_more(_data(**base), [2, 3, 2, 3])

    assert plan.startswith("ELE PEDE MAIS") and "a resposta é DOSE" in plan
    assert "poucas distâncias" in plan and "4 de 4" in plan
    assert chat.startswith("Ele pediu mais em 02/10") and "ELE PEDE MAIS" not in chat


def test_no_request_no_line():

    with _patch_asks(turns=[{"role": "user", "timestamp": "2026-10-02T15:51:00-03:00",
                             "text": "qual o treino de amanhã?"}]):

        assert AthleteDossier._asks_more(_data(today=date(2026, 10, 21)), [3]) == ""


def test_the_perception_section_carries_the_request_even_without_effort_reports():

    with patch(f"{MODULE}.AthleteDossier._asks_more", return_value="ELE PEDE MAIS (teste)"), patch(
        "app.infrastructure.persistence.session_rpe_repository.SessionRpeRepository.load_sessions",
        return_value=[],
    ), patch(
        "app.infrastructure.persistence.checkin_repository.CheckinRepository.load",
        return_value=[],
    ):

        lines = AthleteDossier._perception(_data())

    assert "ELE PEDE MAIS (teste)" in lines
    assert any("Sem relato de esforço" in line for line in lines)
