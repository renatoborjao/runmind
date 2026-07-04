from app.application.planner.strategy.session_composer import (
    SessionComposer,
)

_DAY_INDEX = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}

_QUALITY = {"VO2", "TEMPO", "FARTLEK", "PROGRESSION"}


def _by_day(composed):

    return {c["day"]: c["type"] for c in composed}


def _types(composed):

    return {c["type"] for c in composed}


def test_single_day_is_a_single_easy():

    assert SessionComposer.compose(
        "Intermediate", "BUILD", ["Wednesday"]
    ) == [{"day": "Wednesday", "type": "EASY"}]


def test_two_days_are_easy_and_long():

    by_day = _by_day(
        SessionComposer.compose("Intermediate", "BUILD", ["Tuesday", "Saturday"])
    )

    assert by_day["Tuesday"] == "EASY"
    assert by_day["Saturday"] == "LONG_RUN"


def test_long_run_goes_on_the_last_weekend_day():

    by_day = _by_day(
        SessionComposer.compose(
            "Intermediate", "BUILD",
            ["Tuesday", "Thursday", "Saturday"],
        )
    )

    assert by_day["Saturday"] == "LONG_RUN"


def test_beginner_never_gets_hard_quality():

    composed = SessionComposer.compose(
        "Beginner", "BUILD",
        ["Monday", "Wednesday", "Friday", "Sunday"],
    )

    types = _types(composed)

    assert "VO2" not in types
    assert "TEMPO" not in types
    # mas tem uma qualidade leve (progressivo/fartlek)
    assert types & {"PROGRESSION", "FARTLEK"}


def test_intermediate_build_uses_intervals():

    types = _types(
        SessionComposer.compose(
            "Intermediate", "BUILD",
            ["Tuesday", "Thursday", "Saturday"],
        )
    )

    assert "VO2" in types


def test_base_phase_uses_light_quality_not_intervals():

    types = _types(
        SessionComposer.compose(
            "Intermediate", "BASE",
            ["Tuesday", "Thursday", "Saturday"],
        )
    )

    # base: qualidade leve (tempo/fartlek), sem tiros de VO2
    assert "VO2" not in types
    assert types & {"TEMPO", "FARTLEK"}


def test_five_days_intermediate_has_two_quality():

    composed = SessionComposer.compose(
        "Intermediate", "BUILD",
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"],
    )

    quality = [c for c in composed if c["type"] in _QUALITY]

    assert len(quality) == 2


def test_six_days_includes_a_recovery_run():

    types = _types(
        SessionComposer.compose(
            "Advanced", "BUILD",
            ["Monday", "Tuesday", "Wednesday",
             "Thursday", "Friday", "Saturday"],
        )
    )

    assert "RECOVERY" in types


def test_session_count_and_days_are_preserved():

    days = ["Monday", "Wednesday", "Friday", "Sunday"]

    composed = SessionComposer.compose("Intermediate", "BUILD", days)

    assert len(composed) == len(days)
    assert {c["day"] for c in composed} == set(days)


def test_preferred_long_run_day_is_honored():

    by_day = _by_day(
        SessionComposer.compose(
            "Intermediate", "BUILD",
            ["Tuesday", "Thursday", "Sunday"],
            preferred_long_run_day="Tuesday",
        )
    )

    assert by_day["Tuesday"] == "LONG_RUN"
    assert by_day["Sunday"] != "LONG_RUN"


def test_preferred_day_outside_running_days_falls_back_to_last():

    by_day = _by_day(
        SessionComposer.compose(
            "Intermediate", "BUILD",
            ["Tuesday", "Thursday", "Saturday"],
            preferred_long_run_day="Sunday",
        )
    )

    assert by_day["Saturday"] == "LONG_RUN"


def test_quality_days_are_not_calendar_adjacent():

    composed = SessionComposer.compose(
        "Advanced", "BUILD",
        ["Monday", "Wednesday", "Friday", "Saturday", "Sunday"],
    )

    quality_days = [
        _DAY_INDEX[c["day"]]
        for c in composed
        if c["type"] in _QUALITY
    ]

    for i in range(len(quality_days)):
        for j in range(i + 1, len(quality_days)):
            assert abs(quality_days[i] - quality_days[j]) != 1
