from app.domain.entities.training_load import (
    ACWR_OPTIMAL_MAX,
    acwr_border_label,
)


def test_none_has_no_border():

    assert acwr_border_label(None) is None


def test_just_over_optimal_edge_is_borderline():

    # 1.31 (o caso da Fernanda): CAUTION por meio ponto -> fronteira
    label = acwr_border_label(ACWR_OPTIMAL_MAX + 0.01)

    assert label is not None
    assert "ótima" in label and "atenção" in label


def test_just_under_optimal_edge_is_also_borderline():

    # 1.29: OPTIMAL, mas encostado -> mesma fronteira (simétrico)
    assert acwr_border_label(ACWR_OPTIMAL_MAX - 0.01) is not None


def test_clearly_inside_a_band_is_not_borderline():

    # 1.10 está no meio do ótimo -> sem fronteira
    assert acwr_border_label(1.10) is None
    # 1.70 está fundo no alto -> sem fronteira
    assert acwr_border_label(1.70) is None


def test_caution_edge_is_borderline():

    # 1.47 está a 0.03 de 1.5 -> dentro da margem
    assert acwr_border_label(1.47) is not None


def test_clearly_beyond_margin_is_not_borderline():

    # ACWR real vem arredondado em 2 casas; ~0.07 além do corte já é longe
    assert acwr_border_label(ACWR_OPTIMAL_MAX + 0.07) is None
