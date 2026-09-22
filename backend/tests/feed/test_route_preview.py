from app.presentation.api.v1.feed import _route_preview


def test_none_when_too_few_points():
    assert _route_preview(None) is None
    assert _route_preview([]) is None
    assert _route_preview([{"lat": 1.0, "lon": 2.0}]) is None


def test_ignores_points_without_coords():
    # None/ausente/0 (null-island) caem fora — mesma convenção do app (p.lat && p.lon)
    pts = [{"lat": 0, "lon": 0}, {"lat": None, "lon": 3.0}, {"foo": 1}]
    assert _route_preview(pts) is None  # sobra <2 válidos


def test_downsamples_and_keeps_first_and_last():
    pts = [{"lat": -23.5 + i * 0.001, "lon": -46.6 - i * 0.001} for i in range(200)]

    out = _route_preview(pts, n=24)

    assert out is not None
    assert len(out) <= 26  # ~n + o último anexado
    assert out[0] == [round(pts[0]["lat"], 5), round(pts[0]["lon"], 5)]
    assert out[-1] == [round(pts[-1]["lat"], 5), round(pts[-1]["lon"], 5)]
    # coords arredondadas pra payload leve (5 casas)
    assert all(len(p) == 2 for p in out)


def test_small_route_passes_through():
    pts = [{"lat": 1.111119, "lon": 2.0}, {"lat": 1.2, "lon": 2.1}]

    out = _route_preview(pts)

    assert out == [[1.11112, 2.0], [1.2, 2.1]]
