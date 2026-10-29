"""ESTEIRA (nº 82). Na esteira o relógio não mede o ritmo: o Leonardo correu o ritmo de prova de
09/10 com o relógio descalibrado e, em 23/10, fez os tiros de 400 m na velocidade 11 do painel
(pace 5:27, MAIS rápido que o alvo de 5:40-5:55) — e o sistema leu os dois como forte sem
intensidade. O atleta já contava isso no chat; agora vira registro de execução."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.application.coach.conversation.coach_brain import PROMPT_TEMPLATE, CoachBrain
from app.application.coach.intelligence.perception_recorder import PerceptionRecorder
from app.application.events.training_completed import TrainingCompletedEvent
from app.application.history import treadmill_report as report
from app.application.history.execution_log import ExecutionLog
from app.application.history.stimulus_delivery import DELIVERED, judge
from app.application.history.treadmill_report import blocks_from_report, normalize
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.workout_step import (
    COOLDOWN,
    INTERVAL,
    RECOVERY,
    REPEAT,
    WARMUP,
    WorkoutStep,
)
from tests.coach.factories import make_activity

DAY = date(2026, 10, 23)

MODULE = "app.application.history.treadmill_report"


def _vo2_session():
    """Aquecimento + 6x 400 m a 5:40-5:55 + trote + desaquecimento."""

    steps = [
        WorkoutStep(kind=WARMUP, distance_m=2000),
        WorkoutStep(
            kind=REPEAT, reps=6,
            steps=[
                WorkoutStep(kind=INTERVAL, distance_m=400, pace_min="5:40", pace_max="5:55"),
                WorkoutStep(kind=RECOVERY, distance_m=200),
            ],
        ),
        WorkoutStep(kind=COOLDOWN, distance_m=1500),
    ]

    return PlannedSession(
        day="Friday", workout_type="Velocidade / VO2", objective="", planned_distance_km=7.1,
        planned_duration_minutes=None, target_pace_min="5:40", target_pace_max="5:55", steps=steps,
    )


# --- o que ele conta vira número ---------------------------------------------------------------


def test_a_panel_speed_becomes_a_pace_and_a_typed_pace_is_kept():

    items = normalize([
        {"kind": "interval", "speed_kmh": 11, "meters": 400, "reps": 6},
        {"kind": "run", "pace": "7:30"},
        {"kind": "run", "speed_kmh": "8"},
    ])

    assert [(i["kind"], i["pace"]) for i in items] == [
        ("interval", "5:27"), ("run", "7:30"), ("run", "7:30"),
    ]
    assert items[0]["meters"] == 400 and items[0]["reps"] == 6


def test_nonsense_numbers_are_dropped():

    assert normalize([{"kind": "interval", "pace": "0:45"}]) == []
    assert normalize([{"kind": "run", "speed_kmh": 110}]) == []
    assert normalize([{"kind": "run", "speed_kmh": 0}]) == []
    assert normalize([{"kind": "run"}, "lixo", None]) == []
    assert normalize(None) == [] and normalize("5:27") == []
    # "tiros" também vale como tiro
    assert normalize([{"kind": "tiros", "pace": "5:30"}])[0]["kind"] == "interval"


# --- contra a faixa que o plano prescreveu -----------------------------------------------------


def test_the_reps_are_compared_with_the_prescribed_band_and_faster_is_flagged_as_such():

    items = normalize([
        {"kind": "interval", "speed_kmh": 11, "meters": 400, "reps": 6},
        {"kind": "run", "pace": "7:30"},
    ])

    blocks = blocks_from_report(items, _vo2_session())

    # 6 tiros; o leve solto (sem faixa de contínuo no plano) não entra: só faria ruído
    assert len(blocks) == 6
    assert all(b["kind"] == INTERVAL and b["target"] == "5:40-5:55" for b in blocks)
    assert all(b["pace"] == "5:27" and b["m"] == 400 and b["ok"] is False for b in blocks)

    on_band = blocks_from_report(normalize([{"kind": "interval", "pace": "5:50", "reps": 2}]),
                                 _vo2_session())

    assert [b["ok"] for b in on_band] == [True, True]


def test_when_he_does_not_say_how_many_reps_the_prescribed_number_is_used():
    """Leonardo disse "tiros rápidos de 400 m na velocidade 11" sem contar quantos."""

    items = normalize([{"kind": "interval", "speed_kmh": 11, "meters": 400}])

    assert items[0]["reps"] is None
    assert len(blocks_from_report(items, _vo2_session())) == 6


def test_without_a_session_the_reps_are_still_kept_but_not_judged():

    blocks = blocks_from_report(normalize([{"kind": "interval", "pace": "5:30", "reps": 3}]), None)

    assert len(blocks) == 3 and all(b["target"] is None and b["ok"] is None for b in blocks)


# --- gravação ------------------------------------------------------------------------------------


def _recording():
    """record() com a corrida do dia, o plano e o registro de execução simulados."""

    activity = make_activity(
        id=24824898652, distance=7100.0, moving_time=2820,
        start_date=datetime(2026, 10, 23, 8, 55, tzinfo=UTC),
    )

    plan = MagicMock()

    store = MagicMock()

    patches = [
        patch.object(PerceptionRecorder, "_run_on", return_value=activity),
        patch(
            "app.infrastructure.persistence.weekly_plan_repository.WeeklyPlanRepository",
            return_value=SimpleNamespace(history=lambda profile: [plan], load=lambda profile: None),
        ),
        patch(
            "app.application.planner.weekly_plan_matcher.WeeklyPlanMatcher.pairs",
            return_value=[(_vo2_session(), activity)],
        ),
        patch(
            "app.infrastructure.persistence.execution_log_store.ExecutionLogStore",
            return_value=store,
        ),
    ]

    return patches, store


def test_what_he_told_is_written_to_the_execution_log_as_his_report():

    patches, store = _recording()

    for p in patches:

        p.start()

    try:

        ok = report.record(
            "leonardo", DAY, [{"kind": "interval", "speed_kmh": 11, "meters": 400, "reps": 6}],
        )

    finally:

        for p in patches:

            p.stop()

    assert ok is True

    args = store.record.call_args.args

    assert args[0] == "leonardo" and args[1] == 24824898652 and args[2] == "2026-10-23"
    assert round(args[3], 1) == 7.1

    entry = args[4]

    assert entry["reported"] is True and len(entry["blocks"]) == 6


def test_nothing_is_written_without_a_run_that_day_or_a_comparable_item():

    with patch.object(PerceptionRecorder, "_run_on", return_value=None):

        assert report.record("leonardo", DAY, [{"kind": "interval", "pace": "5:30"}]) is False

    assert report.record("leonardo", DAY, [{"kind": "interval", "pace": "0:30"}]) is False
    assert report.record("leonardo", DAY, None) is False


def test_the_report_beats_the_untrustworthy_watch_in_the_delivery_check():
    """23/10: o relógio na esteira + esforço 3/10 dava 'sem medida'; com o relato (tiros 27 s/km
    mais rápidos que a faixa) o forte é ENTREGUE."""

    items = normalize([{"kind": "interval", "speed_kmh": 11, "meters": 400, "reps": 6}])

    entry = {"blocks": blocks_from_report(items, _vo2_session()), "reported": True}

    treadmill_run = make_activity(raw={"trainer": True})

    item = judge(_vo2_session(), treadmill_run, entry, 3, DAY)

    assert item.verdict == DELIVERED
    assert "6 de 6 blocos no ritmo-alvo ou mais rápido" in item.detail
    assert "relato dele na esteira" in item.detail


def test_the_planned_x_done_line_says_it_is_his_report():

    items = normalize([{"kind": "interval", "speed_kmh": 11, "meters": 400, "reps": 6}])

    entry = {"blocks": blocks_from_report(items, _vo2_session()), "missing": [], "reported": True}

    text = ExecutionLog._blocks_text(entry)

    assert "tiros 6× 400 m" in text and "5:27" in text
    assert "relato dele na esteira (o relógio não mede lá)" in text


# --- o cérebro do chat devolve o relato junto da percepção -----------------------------------


def test_the_brain_returns_the_treadmill_report_inside_the_perception():

    parsed = CoachBrain._parse_perception({
        "day": "2026-10-23", "rpe": None, "feel": None,
        "treadmill": [{"kind": "interval", "speed_kmh": 11, "meters": 400, "reps": 6}],
    })

    # só a esteira, sem esforço nem palavras, já vale
    assert parsed["treadmill"][0]["pace"] == "5:27"

    # lixo na esteira não derruba a percepção de sempre
    plain = CoachBrain._parse_perception(
        {"day": "2026-10-23", "rpe": 3, "feel": "tranquilo", "treadmill": [{"pace": "0:10"}]}
    )

    assert plain == {"day": "2026-10-23", "rpe": 3, "feel": "tranquilo"}

    junk_only = {"day": "2026-10-23", "treadmill": [{"pace": "0:10"}]}

    assert CoachBrain._parse_perception(junk_only) is None


def test_the_chat_prompt_teaches_the_treadmill_report_and_still_formats():

    flat = " ".join(PROMPT_TEMPLATE.split())

    assert "ESTEIRA: se ele conta que correu na esteira" in flat
    assert '"treadmill"' in PROMPT_TEMPLATE

    PROMPT_TEMPLATE.format(
        runner_name="Leonardo", voice="", context_facts="", pending_block="", history_block="",
        cards="race", message="oi",
    )


def test_the_chat_perception_hands_the_report_to_the_recorder():

    with (
        patch(f"{MODULE}.record") as record,
        patch.object(PerceptionRecorder, "_run_on", return_value=None),
        patch("app.application.coach.intelligence.perception_recorder.today_local",
              return_value=date(2026, 10, 24)),
    ):

        PerceptionRecorder.from_chat("leonardo", {
            "day": "2026-10-23", "rpe": None, "feel": None,
            "treadmill": [{"kind": "interval", "pace": "5:27"}],
        })

    record.assert_called_once()
    assert record.call_args.args[0] == "leonardo" and record.call_args.args[1] == DAY


# --- o pós-treino pergunta a velocidade -----------------------------------------------------


def _result(activity, label="Velocidade / VO2"):

    enriched = SimpleNamespace(activity=activity, training_type="")

    return {"activity": enriched, "planned_session": SimpleNamespace(workout_type=label)}


def test_after_a_strong_treadmill_run_the_coach_asks_for_the_panel_speed():

    run = make_activity(id=7, raw={"trainer": True})

    with patch(
        "app.infrastructure.persistence.execution_log_store.ExecutionLogStore"
    ) as store:

        store.return_value.all.return_value = {}

        out = TrainingCompletedEvent._ask_treadmill("leonardo", _result(run), "análise")

    assert out.startswith("análise\n\n") and "velocidade do painel (km/h)" in out


def test_no_question_outdoors_on_an_easy_run_or_when_he_already_told():

    treadmill = make_activity(id=7, raw={"trainer": True})

    outdoor = make_activity(id=8, raw={})

    with patch(
        "app.infrastructure.persistence.execution_log_store.ExecutionLogStore"
    ) as store:

        store.return_value.all.return_value = {}

        assert TrainingCompletedEvent._ask_treadmill("l", _result(outdoor), "x") == "x"
        assert TrainingCompletedEvent._ask_treadmill(
            "l", _result(treadmill, "Rodagem Leve"), "x",
        ) == "x"

        store.return_value.all.return_value = {7: {"reported": True, "blocks": []}}

        assert TrainingCompletedEvent._ask_treadmill("l", _result(treadmill), "x") == "x"

    # a gravação chamada "esteira" também conta
    named = make_activity(id=9, name="Corrida em esteira", raw={})

    assert report.is_treadmill(named) is True
