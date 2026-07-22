from app.application.coach.intelligence.body_reading_builder import (
    BodyReadingBuilder,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_BUILDING,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    RISING,
    STABLE,
    RecoveryTrend,
)
from app.domain.entities.training_load import (
    LOAD_DETRAINING,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_OPTIMAL,
)


def _rec(hrv=STABLE, rhr=STABLE, sleep=7.5, short=0, nights=10, stress=25):

    return RecoveryTrend(
        hrv_direction=hrv,
        rhr_direction=rhr,
        sleep_avg_hours=sleep,
        short_nights=short,
        nights_counted=nights,
        stress_avg=stress,
        days_covered=nights,
    )


# ---------------- veredito: carga À LUZ da recuperação ----------------


def test_high_load_with_good_recovery_is_absorbing():

    # a régua central: rampou MAS o corpo absorve -> não é sobrecarga
    state = BodyReadingBuilder._verdict(LOAD_HIGH, _rec(hrv=RISING, rhr=RISING))

    assert state == BODY_ABSORBING


def test_high_load_with_declining_recovery_is_strained():

    state = BodyReadingBuilder._verdict(LOAD_HIGH, _rec(hrv=FALLING))

    assert state == BODY_STRAINED


def test_optimal_load_with_declining_recovery_flags_recovery():

    # carga ok, mas recuperação caindo: o problema não é treino
    state = BodyReadingBuilder._verdict(LOAD_OPTIMAL, _rec(rhr=FALLING))

    assert state == BODY_RECOVERY_FLAG


def test_optimal_load_with_good_recovery_is_balanced():

    state = BodyReadingBuilder._verdict(LOAD_OPTIMAL, _rec())

    assert state == BODY_BALANCED


def test_detraining_with_good_recovery_is_fresh():

    state = BodyReadingBuilder._verdict(LOAD_DETRAINING, _rec())

    assert state == BODY_FRESH


def test_insufficient_load_good_recovery_is_building():

    state = BodyReadingBuilder._verdict(LOAD_INSUFFICIENT, _rec())

    assert state == BODY_BUILDING


def test_insufficient_load_declining_recovery_flags_recovery():

    state = BodyReadingBuilder._verdict(LOAD_INSUFFICIENT, _rec(hrv=FALLING))

    assert state == BODY_RECOVERY_FLAG


# ---------------- limitador acionável ----------------


def test_limiter_sleep_on_many_short_nights():

    assert BodyReadingBuilder._limiter(_rec(sleep=5.3, short=7, nights=11)) == "sono"


def test_limiter_resting_hr_when_worsening():

    # sono ok, mas FC repouso piorando
    rec = _rec(sleep=7.5, short=0, rhr=FALLING)

    assert BodyReadingBuilder._limiter(rec) == "fc_repouso"


def test_limiter_stress_when_high():

    rec = _rec(sleep=7.5, short=0, stress=45)

    assert BodyReadingBuilder._limiter(rec) == "stress"


def test_no_limiter_when_all_good():

    assert BodyReadingBuilder._limiter(_rec()) is None
