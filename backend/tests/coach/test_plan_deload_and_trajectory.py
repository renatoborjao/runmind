"""A semana de descarga que o coach monta tem que ser CERTA e EXPLICADA, e o plano
não pode ficar parado. Caso real — Maurício, 19/10: o plano veio 40% mais leve
(27 km contra 43 feitos) por um sinal "4 semanas seguidas de carga" que não viu o
recuo de 28/09 (31 km depois de 47: a carga caiu só 24%, o corte era 30%), na 3ª
semana de um bloco de 4 cuja descarga era a 4ª; o rótulo dizia "construir" e o
objetivo "descarga"; a razão não ficou guardada (o sinal some no dia seguinte)."""

import asyncio
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.application.coach.context.athlete_dossier import AthleteDossier, _Inputs
from app.application.coach.planning.ai_plan_service import AIPlanService
from app.application.coach.planning.coach_plan_engine import CoachPlanEngine
from app.application.coach.planning.plan_context_builder import PlanContextBuilder
from app.application.history.deload_analyzer import (
    DeloadAnalyzer,
    block_deload_position,
    deload_directive,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.body_reading import FALLING, STABLE, RecoveryTrend
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)
from tests.coach.factories import make_activity, make_runner

MODULE = "app.application.coach.planning.ai_plan_service"


def _recovery(hrv=STABLE, rhr=STABLE) -> RecoveryTrend:

    return RecoveryTrend(hrv_direction=hrv, rhr_direction=rhr, days_covered=7)


# Maurício na noite de 18/10 (cargas semanais: 21/09, 28/09, 05/10, 12/10)
MAURICIO_LOADS = [343.5, 260.9, 306.4, 350.3]

BLOCK_ROLES = [
    "Semana 1: Variação de ritmo com Fartlek e longão progressivo disciplinado",
    "Semana 2: VO2 longo para potência aeróbica e aumento de volume no final de semana",
    "Semana 3: Inserção de simulado inicial com bloco longo no ritmo-alvo de prova",
    "Semana 4: Semana de descarga com redução de volume para consolidar ganhos",
]


# ---- o sinal de descarga -----------------------------------------------------


def test_a_week_20_percent_below_the_peak_is_a_recovery_week():
    """28/09: 261 contra o pico de 343 (razão 0.76). Reinicia a contagem — o bloco
    de carga do Maurício tinha 2 semanas, não 4."""

    d = DeloadAnalyzer.assess(MAURICIO_LOADS, _recovery(), acwr=1.11)

    assert d.building_weeks == 2
    assert d.due is False
    assert deload_directive(d) == ""


def test_a_normal_fluctuation_does_not_reset_the_block():
    """A contagem segue lendo 4 semanas seguidas — mas é só informação: com o corpo
    firme, nada de descarga."""

    d = DeloadAnalyzer.assess([300, 270, 310, 320], _recovery(), acwr=1.2)

    assert d.building_weeks == 4
    assert d.due is False


def test_block_position_finds_where_the_deload_falls():

    assert block_deload_position(BLOCK_ROLES, 3) == (False, 1)
    assert block_deload_position(BLOCK_ROLES, 4) == (True, None)
    assert block_deload_position(BLOCK_ROLES, 1) == (False, 3)
    assert block_deload_position(None, 2) == (False, None)
    assert block_deload_position(BLOCK_ROLES, 9) == (False, None)
    assert block_deload_position([], None) == (False, None)


def test_the_block_that_plans_a_future_deload_does_not_hold_back_a_tired_body():
    """O corpo cansado antecipa a descarga mesmo que o bloco a ponha só daqui a 2
    semanas — o bloco é hipótese, o corpo é fato."""

    d = DeloadAnalyzer.assess(
        [300, 310, 320], _recovery(hrv=FALLING), acwr=1.2,
    )

    assert d.due is True
    assert "recuperação está caindo" in d.reason


def test_the_directive_asks_for_the_why_with_the_athletes_numbers():

    d = DeloadAnalyzer.assess([300, 310, 320, 330], _recovery(hrv=FALLING), acwr=1.2)

    text = deload_directive(d)

    assert '"is_deload": true' in text
    assert '"deload_why"' in text
    assert "NÚMEROS DELE" in text
    assert "ACWR" in text  # só pra proibir o jargão
    assert "nada de ACWR" in text


# ---- o plano da IA -------------------------------------------------------------


def _ai_json(**extra) -> str:

    data = {
        "weekly_objective": "semana",
        "phase": "BUILD",
        "sessions": [
            {"day": "Tuesday", "kind": "run", "workout_type": "Rodagem",
             "distance_km": 6.0, "pace_min": "6:20", "pace_max": "6:50",
             "structure": ["6 km leves"], "purpose": "base"},
        ],
    }

    data.update(extra)

    return json.dumps(data)


def _parse(**extra) -> TrainingPlan:

    return CoachPlanEngine._to_plan(
        _ai_json(**extra), "Mauricio", "15k", date(2026, 10, 19),
    )


def test_the_plan_carries_the_deload_and_its_why():

    plan = _parse(
        is_deload=True,
        deload_why="Você fez 47, 32, 39 e 43 km; esta semana é mais leve pra "
                   "consolidar antes do simulado.",
    )

    assert plan.is_deload is True
    assert plan.deload_why.startswith("Você fez 47")


def test_a_normal_week_has_no_deload_and_no_why():

    plan = _parse(is_deload=False, deload_why="razão solta")

    assert plan.is_deload is False
    assert plan.deload_why is None

    assert _parse().is_deload is False


def test_a_deload_without_why_stays_a_deload():

    plan = _parse(is_deload=True, deload_why="null")

    assert plan.is_deload is True
    assert plan.deload_why is None


def test_the_prompt_teaches_the_coach_to_explain_and_to_follow_the_block():

    from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE

    assert '"is_deload"' in PROMPT_TEMPLATE
    assert '"deload_why"' in PROMPT_TEMPLATE
    assert "REDEFINA" in PROMPT_TEMPLATE
    assert "descarga não" in PROMPT_TEMPLATE


def test_the_why_survives_the_disk_roundtrip():

    plan = _parse(is_deload=True, deload_why="porque sim, com 43 km")

    again = WeeklyPlanRepository._from_dict(WeeklyPlanRepository._to_dict(plan))

    assert again.is_deload is True
    assert again.deload_why == "porque sim, com 43 km"

    legacy = WeeklyPlanRepository._to_dict(plan)

    legacy.pop("deload_why")

    assert WeeklyPlanRepository._from_dict(legacy).deload_why is None


def test_the_message_and_the_app_show_the_why():

    plan = _parse(is_deload=True, deload_why="Você fez 43 km; semana mais leve.")

    text = WeeklyPlanMessageFormatter.format("Mauricio", plan)

    assert "Semana mais leve de propósito — Você fez 43 km; semana mais leve." in text

    shown = _screen(plan)

    assert shown["is_deload"] is True
    assert shown["deload_why"] == "Você fez 43 km; semana mais leve."


def _screen(plan) -> dict:
    """A tela Treino do atleta — mesmo helper dos testes do plano da semana."""

    from tests.home.test_week_plan_builder import _build

    return _build(plan, now=datetime(2026, 10, 20, 9, 0, 0))


def test_the_block_label_says_when_the_week_is_a_deload():

    plan = _parse(is_deload=True)

    repo = MagicMock()

    block = {"weeks": 4, "focus": "Construir a resistência para os 15K",
             "weeks_plan": BLOCK_ROLES, "start": "2026-10-05"}

    with patch.object(AIPlanService, "_active_block", return_value=(block, 3)):

        AIPlanService._stamp_block(repo, "p", plan)

    assert plan.block_label == (
        "semana 3 de 4 — Construir a resistência para os 15K · semana de descarga"
    )


# ---- o dossiê guarda a razão ---------------------------------------------------


def test_the_dossier_carries_the_why_so_the_chat_can_explain():
    """O sinal de carga que motivou a descarga some no dia seguinte (ACWR 0.93 em
    19/10); a razão tem que viver no plano."""

    plan = _parse(is_deload=True, deload_why="Você fez 47, 32, 39 e 43 km.")

    plan.week_start = date(2026, 10, 19)

    data = _Inputs(profile="p", today=date(2026, 10, 20))

    data.plan = plan
    data.history = SimpleNamespace(activities=[])

    lines = AthleteDossier._plan_week(data)

    joined = "\n".join(lines)

    assert "ESTA SEMANA É DE DESCARGA" in joined
    assert "Você fez 47, 32, 39 e 43 km." in joined
    assert "por que diminuiu" in joined


def test_the_dossier_finds_where_the_block_puts_the_deload():

    data = _Inputs(profile="p", today=date(2026, 10, 18))

    block = {"weeks": 4, "focus": "x", "weeks_plan": BLOCK_ROLES,
             "start": "2026-10-05"}

    with patch.object(AIPlanService, "_active_block", return_value=(block, 3)):

        assert AthleteDossier._block_deload(data, date(2026, 10, 19)) == (False, 1)

    with patch.object(AIPlanService, "_active_block", return_value=None):

        assert AthleteDossier._block_deload(data, date(2026, 10, 19)) == (False, None)

    with patch.object(AIPlanService, "_active_block", side_effect=RuntimeError):

        assert AthleteDossier._block_deload(data, date(2026, 10, 19)) == (False, None)


# ---- a trajetória: o plano que parou ------------------------------------------


def _session(day, kind, km, low="6:20", high="6:50") -> PlannedSession:

    return PlannedSession(
        day=day, workout_type=kind, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=low, target_pace_max=high,
    )


def _week(monday, sessions, volume) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="M", objective="15k", phase="BUILD", weekly_volume=volume,
        running_days=[s.day for s in sessions], week_start=monday,
        sessions=sessions,
    )


# o plano do Maurício nas 6 semanas até 12/10 (planejado), como estava na VM
MAURICIO_PLANS = [
    _week(date(2026, 9, 7), [_session("Tuesday", "Fartlek", 8.0, "5:20", "6:00"),
                             _session("Sunday", "Rodagem leve", 7.0)], 15.0),
    _week(date(2026, 9, 14), [_session("Tuesday", "Tempo Run / Limiar", 8.0, "5:40", "6:10"),
                              _session("Thursday", "Rodagem", 8.0),
                              _session("Saturday", "Prova 10km", 10.0, "5:20", "5:55")], 26.0),
    _week(date(2026, 9, 21), [_session("Tuesday", "Intervalado Curto", 7.2, "5:40", "6:00"),
                              _session("Friday", "Rodagem", 8.5),
                              _session("Saturday", "Longão Progressivo", 12.0, "5:40", "6:40"),
                              ], 27.7),
    _week(date(2026, 9, 28), [_session("Tuesday", "Limiar Intervalado", 8.5, "5:45", "5:55"),
                              _session("Thursday", "Rodagem com Acelerações", 7.5),
                              _session("Sunday", "Longão Aeróbico", 13.0)], 29.0),
    _week(date(2026, 10, 5), [_session("Tuesday", "Fartlek", 8.0, "5:20", "5:40"),
                              _session("Thursday", "Rodagem Leve", 8.0),
                              _session("Saturday", "Longão Progressivo", 12.0, "5:40", "6:40"),
                              ], 34.0),
    _week(date(2026, 10, 12), [_session("Monday", "Limiar Intervalado", 9.0, "5:30", "5:45"),
                               _session("Thursday", "Rodagem Leve", 8.0),
                               _session("Saturday", "Simulado", 14.0, "5:30", "5:45")], 36.0),
]

FIFTEEN_K = TrainingGoal(
    name="baixar pace", distance_km=15.0, target_time="01:22:30",
    race_date=date(2026, 12, 20), priority="A",
)


def test_the_trajectory_shows_the_numbers_of_a_plan_that_stopped():

    line = PlanContextBuilder._trajectory_line(
        MAURICIO_PLANS, [10.0, 14.0, 10.0, 15.0, 14.0, 14.0], FIFTEEN_K,
    )

    assert "TRAJETÓRIA DOS ESTÍMULOS" in line
    assert "Volume planejado (km): 15 · 26 · 28 · 29 · 34 · 36" in line
    assert "12 km (Longão Progressivo, 5:40–6:40)" in line
    assert "13 km (Longão Aeróbico, 6:20–6:50)" in line
    assert "Treinos fortes:" in line
    assert "Fartlek 8 km @5:20–5:40" in line
    # rodagem/leve não é treino forte
    assert "Rodagem Leve" not in line.split("Treinos fortes:")[1].split("\n")[0]
    assert "Maior corrida FEITA em cada semana (km): 10 · 14 · 10 · 15 · 14 · 14" in line
    # o longão do plano vs a prova de 15 km
    assert "a maior corrida feita nestas semanas foi 15 km" in line
    assert "~16–19 km" in line
    assert "LEIA A TRAJETÓRIA" in line
    assert "é parar" in line
    # evoluir é em CADA tipo de treino, não só no longão — e o leve segue leve
    assert "não só o longão" in line
    assert "CADA tipo de treino evolui na SUA dimensão" in line
    assert "O forte aproxima o pace do alvo" in line
    assert "o leve segue leve DE VERDADE" in line
    assert "nunca vira mais um forte" in line


def test_the_trajectory_needs_a_few_weeks_to_say_anything():

    assert PlanContextBuilder._trajectory_line(MAURICIO_PLANS[:2], [], FIFTEEN_K) == ""
    assert PlanContextBuilder._trajectory_line([], [], None) == ""


def test_the_trajectory_works_without_a_race_or_done_runs():

    line = PlanContextBuilder._trajectory_line(MAURICIO_PLANS, [], None)

    assert "TRAJETÓRIA" in line
    assert "Maior corrida FEITA em cada semana" not in line
    assert "Prova-âncora" not in line


def test_the_peak_long_run_reference_follows_the_race_distance():

    assert PlanContextBuilder._peak_long_run(5.0) == (9, 12)
    assert PlanContextBuilder._peak_long_run(10.0) == (13, 16)
    assert PlanContextBuilder._peak_long_run(15.0) == (16, 19)
    assert PlanContextBuilder._peak_long_run(21.0975) == (18, 22)
    assert PlanContextBuilder._peak_long_run(42.195) == (30, 35)


def test_the_context_carries_the_trajectory():

    context = PlanContextBuilder.build(
        runner=make_runner(preferred_running_days=["Tuesday", "Thursday"]),
        goal=FIFTEEN_K, week_start=date(2026, 10, 19),
        recent_plans=MAURICIO_PLANS, longest_runs=[10.0, 14.0, 10.0, 15.0, 14.0, 14.0],
    )

    assert "TRAJETÓRIA DOS ESTÍMULOS" in context
    assert "AS ÚLTIMAS SEMANAS, dia a dia" in context


# ---- os dias que o atleta reorganizou -----------------------------------------


def test_a_rebuilt_week_keeps_the_days_the_athlete_moved():
    """Maurício 19/10 moveu 4 sessões pelo app (qua/sex/dom); a rotina é ter/qui/
    sáb/dom. Refazer a semana não pode devolver tudo pros dias do perfil."""

    context = PlanContextBuilder.build(
        runner=make_runner(
            preferred_running_days=["Tuesday", "Thursday", "Saturday", "Sunday"],
        ),
        goal=FIFTEEN_K, week_start=date(2026, 10, 19), today=date(2026, 10, 19),
        week_days=["Wednesday", "Friday", "Sunday"],
    )

    assert "Dias de corrida que ainda faltam NESTA semana" in context
    assert "quarta-feira, sexta-feira, domingo" in context.lower()
    assert "JÁ reorganizou" in context
    assert "a rotina fixa é terça-feira" in context.lower()
    assert "Dias de corrida dele:" not in context


def test_without_a_moved_week_the_routine_days_rule_stands():

    context = PlanContextBuilder.build(
        runner=make_runner(preferred_running_days=["Tuesday", "Thursday"]),
        goal=FIFTEEN_K, week_start=date(2026, 10, 19),
    )

    assert "Dias de corrida dele: terça-feira, quinta-feira" in context.lower() or (
        "Dias de corrida dele:" in context
    )
    assert "ainda faltam NESTA semana" not in context


def test_remaining_days_are_the_ones_still_to_come_minus_today_if_done():

    existing = _week(
        date(2026, 10, 19),
        [_session("Monday", "Regenerativo", 4.0),
         _session("Wednesday", "Velocidade", 7.1),
         _session("Friday", "Rodagem", 6.0),
         _session("Sunday", "Longão", 10.0)],
        27.1,
    )

    ran_monday = make_activity(
        id=1, start_date=datetime(2026, 10, 19, 7, 0), distance=4160.0,
        moving_time=1800,
    )

    history = SimpleNamespace(activities=[ran_monday])

    with patch(f"{MODULE}.today_local", return_value=date(2026, 10, 19)):

        assert AIPlanService._remaining_days(existing, history) == [
            "Wednesday", "Friday", "Sunday",
        ]

    with patch(f"{MODULE}.today_local", return_value=date(2026, 10, 19)):

        # sem ter corrido hoje, o dia de hoje ainda conta
        assert AIPlanService._remaining_days(
            existing, SimpleNamespace(activities=[]),
        ) == ["Monday", "Wednesday", "Friday", "Sunday"]


def test_longest_run_done_in_each_week():

    plans = MAURICIO_PLANS[-2:]

    acts = [
        make_activity(id=1, start_date=datetime(2026, 10, 6, 7), distance=8000.0),
        make_activity(id=2, start_date=datetime(2026, 10, 10, 7), distance=15000.0),
        make_activity(id=3, start_date=datetime(2026, 10, 17, 7), distance=14000.0),
        make_activity(id=4, start_date=datetime(2026, 10, 17, 9), distance=3000.0,
                      sport="Walk"),
    ]

    out = AIPlanService._longest_runs(SimpleNamespace(activities=acts), plans)

    assert out == [15.0, 14.0]

    assert AIPlanService._longest_runs(SimpleNamespace(activities=[]), plans) == [0.0, 0.0]


def test_ensure_plan_passes_the_moved_days_when_rebuilding_the_current_week():

    week = date(2026, 10, 19)

    existing = _week(
        week,
        [_session("Monday", "Regenerativo", 4.0),
         _session("Wednesday", "Velocidade", 7.1)],
        11.1,
    )

    captured = {}

    def fake_context(*args, **kwargs):

        captured.update(kwargs)

        return "ctx"

    ai_plan = _week(week, [_session("Wednesday", "Rodagem", 8.0)], 8.0)

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as repo_cls,
        patch(f"{MODULE}.WeeklyPlanService") as wps,
        patch(f"{MODULE}.today_local", return_value=date(2026, 10, 19)),
        patch.object(AIPlanService, "_build_context", side_effect=fake_context),
        patch.object(AIPlanService, "_generate_ai", return_value=ai_plan),
        patch.object(AIPlanService, "_remaining_days", return_value=["Wednesday"]),
        patch.object(AIPlanService, "_stamp_block"),
    ):

        repo_cls.return_value.load.return_value = existing
        wps.active_week_start.return_value = week

        runner = make_runner()

        asyncio.run(
            AIPlanService.ensure_plan(
                "p", runner, MagicMock(run_walk=False), MagicMock(),
                MagicMock(name="goal"), SimpleNamespace(activities=[]),
                reference_date=date(2026, 10, 19), force=True,
            )
        )

    assert captured["week_days"] == ["Wednesday"]


def test_timedelta_import_is_in_place():
    """_longest_runs soma 6 dias à segunda — o import tem que existir."""

    assert timedelta(days=6).days == 6


def test_a_correction_tells_the_coach_the_old_plan_was_wrong():
    """Refazer porque o plano saiu errado NÃO é pedido do atleta — e o que o plano
    antigo disse (as mensagens que o dossiê lembra) não pode ser defendido."""

    context = PlanContextBuilder.build(
        runner=make_runner(preferred_running_days=["Tuesday"]),
        goal=FIFTEEN_K, week_start=date(2026, 10, 19),
        correction="A descarga era da semana 4 do bloco, não desta.",
    )

    assert "CORREÇÃO DO PLANO" in context
    assert "NÃO foi pedido do atleta" in context
    assert "A descarga era da semana 4 do bloco, não desta." in context
    assert "SUBSTITUÍDO" in context
    # o atleta lê o plano: o erro não vaza pro texto dele (o aviso é à parte)
    assert "NÃO escreva sobre o erro" in context
    assert "mensagem separada" in context
    assert "PEDIDO DO ATLETA AGORA" not in context

    plain = PlanContextBuilder.build(
        runner=make_runner(preferred_running_days=["Tuesday"]),
        goal=FIFTEEN_K, week_start=date(2026, 10, 19),
    )

    assert "CORREÇÃO DO PLANO" not in plain


def test_ensure_plan_forwards_the_correction_to_the_context():

    week = date(2026, 10, 19)

    captured = {}

    def fake_context(*args, **kwargs):

        captured.update(kwargs)

        return "ctx"

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as repo_cls,
        patch(f"{MODULE}.WeeklyPlanService") as wps,
        patch(f"{MODULE}.today_local", return_value=date(2026, 10, 19)),
        patch.object(AIPlanService, "_build_context", side_effect=fake_context),
        patch.object(
            AIPlanService, "_generate_ai",
            return_value=_week(week, [_session("Wednesday", "Rodagem", 8.0)], 8.0),
        ),
        patch.object(AIPlanService, "_stamp_block"),
    ):

        repo_cls.return_value.load.return_value = None
        wps.active_week_start.return_value = week

        asyncio.run(
            AIPlanService.ensure_plan(
                "p", make_runner(), MagicMock(run_walk=False), MagicMock(),
                MagicMock(name="goal"), SimpleNamespace(activities=[]),
                reference_date=week, force=True, correction="erro X",
            )
        )

    assert captured["correction"] == "erro X"


# ---- a descarga que o BLOCO planejou é condicional ----------------------------
# Maurício: o bloco de 05/10 pôs a descarga em 26/10 (semana 4), depois de uma
# semana já mais leve (37 km contra 43). Sem carga elevada, a descarga ali só
# destreina — o papel escrito semanas antes não pode mandar sozinho.


def test_the_blocks_deload_is_skipped_when_the_body_does_not_ask():
    """Maurício 25/10: o papel de descarga do bloco (escrito em 05/10) não vale com o
    corpo firme — o coach é avisado e segue a progressão."""

    d = DeloadAnalyzer.assess(
        [350, 260, 306, 290], _recovery(), acwr=0.93, block_deload_this_week=True,
    )

    assert d.due is False
    assert d.block_skipped is True
    assert "o corpo não a pede" in d.reason

    text = deload_directive(d)

    assert "O BLOCO previa DESCARGA" in text
    assert "DESTREINA" in text
    assert "NÃO vale hoje" in text
    assert 'REDEFINA "block"' in text
    assert "ESPAÇO PRA PUXAR" in text


def test_the_blocks_deload_is_skipped_even_with_elevated_load_if_the_body_is_fine():
    """Carga em alta com HRV estável é o atleta subindo — o bloco não decide."""

    d = DeloadAnalyzer.assess(
        [300, 310], _recovery(), acwr=1.15, block_deload_this_week=True,
    )

    assert d.due is False
    assert d.block_skipped is True


def test_the_blocks_deload_holds_when_the_body_confirms_it():
    """O bloco previa a descarga E a recuperação está caindo com carga em alta."""

    d = DeloadAnalyzer.assess(
        [300, 310], _recovery(hrv=FALLING), acwr=1.15, block_deload_this_week=True,
    )

    assert d.due is True
    assert d.block_skipped is False
    assert "o corpo confirma" in d.reason
    assert deload_directive(d).startswith("SINAL DE DESCARGA")


def test_the_blocks_deload_is_not_forced_by_a_low_load_recovery_dip():
    """Recuperação caindo com a carga BAIXA não é carga: o bloco não ganha a
    descarga por causa disso."""

    d = DeloadAnalyzer.assess(
        [300, 310], _recovery(hrv=FALLING), acwr=0.93, block_deload_this_week=True,
    )

    assert d.due is False
    assert d.block_skipped is True


def test_the_blocks_deload_without_acwr_data_still_needs_the_body():

    skipped = DeloadAnalyzer.assess([300, 310], _recovery(), block_deload_this_week=True)

    assert skipped.due is False and skipped.block_skipped is True

    held = DeloadAnalyzer.assess(
        [300, 310], _recovery(rhr=FALLING), block_deload_this_week=True,
    )

    assert held.due is True


def test_without_a_block_fatigue_still_does_not_beat_a_low_load():
    """A guarda de setembro (ACWR 0.97 + FC de repouso caindo, sem bloco) segue."""

    d = DeloadAnalyzer.assess(
        [294, 151, 344, 252], _recovery(rhr=FALLING), acwr=0.97,
    )

    assert d.due is False
    assert d.block_skipped is False
    assert deload_directive(d) == ""


def test_taper_and_post_race_still_win_over_the_block():

    d = DeloadAnalyzer.assess(
        [300, 310], _recovery(), acwr=1.3, weeks_to_race=2,
        block_deload_this_week=True,
    )

    assert d.due is False
    assert "taper" in d.reason


def test_the_block_line_warns_when_the_weeks_role_is_a_deload():
    """O coach lê o papel da semana no BLOCO EM ANDAMENTO: se é de descarga, a
    linha diz que ele foi escrito sem saber como o atleta chegaria."""

    block = {"weeks": 4, "focus": "Construir a resistência", "weeks_plan": BLOCK_ROLES,
             "start": "2026-10-05"}

    deload_week = AIPlanService._block_line((block, 4))

    assert "ESTA semana: Semana 4: Semana de descarga" in deload_week
    assert "ATENÇÃO" in deload_week
    assert "descarga NÃO é calendário" in deload_week
    assert "só vale se o corpo pedir" in deload_week
    assert "descarga só destreina" in deload_week
    assert "ESPAÇO PRA PUXAR" in deload_week

    build_week = AIPlanService._block_line((block, 3))

    assert "ESTA semana: Semana 3: Inserção de simulado" in build_week
    assert "ATENÇÃO" not in build_week


def test_is_deload_role():

    from app.application.history.deload_analyzer import is_deload_role

    assert is_deload_role("Semana 4: Semana de descarga com redução de volume")
    assert is_deload_role("alívio no fim do bloco")
    assert not is_deload_role("Semana 3: simulado no ritmo-alvo")
    assert not is_deload_role(None)


def test_the_prompt_says_not_to_deload_without_a_tired_body_even_if_the_block_says_so():

    from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE

    assert "NÃO descarregue" in PROMPT_TEMPLATE
    assert "semana leve sobre semana já leve só destreina" in PROMPT_TEMPLATE
    assert "Descarga NÃO é calendário" in PROMPT_TEMPLATE
    assert "segue EVOLUINDO" in PROMPT_TEMPLATE


def test_the_prompt_tells_the_coach_to_push_and_keeps_only_the_ceiling_of_the_jump():

    from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE

    assert "PUXE" in PROMPT_TEMPLATE
    assert "ESPAÇO PRA PUXAR" in PROMPT_TEMPLATE
    assert "Conservador demais é desperdiçar" in PROMPT_TEMPLATE
    # a qualidade sobe em TODOS os tipos de treino, não só no longão
    assert "qualidade em TODOS os tipos de treino, não só no longão" in PROMPT_TEMPLATE
    assert "o leve segue leve DE VERDADE" in PROMPT_TEMPLATE
    assert "o teto é o SALTO, não o passo" in PROMPT_TEMPLATE
    # o bloco não reserva mais a última semana pra aliviar
    assert "alívio só se o corpo pedir" in PROMPT_TEMPLATE


def test_a_new_block_is_not_told_to_reserve_a_deload_week():

    text = AIPlanService._block_line(None)

    assert "Descarga NÃO é item de calendário" in text
    assert "consolidando/testando" in text
