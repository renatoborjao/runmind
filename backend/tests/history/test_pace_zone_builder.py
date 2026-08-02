from app.application.history.pace_zone_builder import PaceZoneBuilder
from app.domain.entities.pace_model import SOURCE_VDOT, PaceModel


def _model(
    easy_min=5.98,
    easy_max=6.72,
    marathon=5.39,
    threshold=5.09,
    interval=4.69,
    rep=4.42,
) -> PaceModel:
    """PaceModel tipo VDOT 40 (corredor de 50 min nos 10k)."""

    return PaceModel(
        easy_min=easy_min,
        easy_max=easy_max,
        marathon=marathon,
        threshold=threshold,
        interval=interval,
        rep=rep,
        vdot=40.0,
        source=SOURCE_VDOT,
    )


def test_build_returns_five_zones_in_order():

    zones = PaceZoneBuilder.build(_model()).zones

    assert [z.number for z in zones] == [1, 2, 3, 4, 5]


def test_each_zone_fast_is_faster_than_slow():

    for zone in PaceZoneBuilder.build(_model()).zones:

        assert zone.fast <= zone.slow


def test_zones_are_contiguous_and_intensify():
    """As faixas encostam sem buraco e a intensidade sobe (pace cai) do Z1
    (leve) pro Z5 (forte). Cada zona É uma faixa E/M/T/I/R do modelo."""

    by_num = {z.number: z for z in PaceZoneBuilder.build(_model()).zones}

    assert by_num[1].fast == by_num[2].slow
    assert by_num[2].fast == by_num[3].slow
    assert by_num[3].fast == by_num[4].slow
    assert by_num[4].fast == by_num[5].slow

    fasts = [by_num[n].fast for n in (1, 2, 3, 4, 5)]

    assert fasts == sorted(fasts, reverse=True)


def test_zones_map_to_model_paces():
    """Z2 = faixa fácil, Z4 fast = limiar, Z5 fast = intervalado — a zona é a
    fonte, não um segundo modelo."""

    model = _model()

    by_num = {z.number: z for z in PaceZoneBuilder.build(model).zones}

    assert by_num[2].fast == model.easy_min
    assert by_num[2].slow == model.easy_max
    assert by_num[4].fast == model.threshold
    assert by_num[5].fast == model.interval


def test_zones_scale_with_a_faster_model():
    """Modelo mais rápido -> todas as faixas ficam mais rápidas."""

    slow = PaceZoneBuilder.build(_model()).zones

    fast = PaceZoneBuilder.build(
        _model(
            easy_min=5.3, easy_max=6.0, marathon=4.7,
            threshold=4.4, interval=4.0, rep=3.8,
        )
    ).zones

    for a, b in zip(slow, fast):

        assert b.fast < a.fast
