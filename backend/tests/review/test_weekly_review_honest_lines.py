"""Frases fixas do resumo de domingo que contradiziam os próprios números (revisão 17/11)."""

from types import SimpleNamespace

from app.application.coach.writer.state_portrait_writer import StatePortraitWriter
from app.application.history.evolution_analyzer import EvolutionAnalyzer
from app.application.review.weekly_review_message_formatter import (
    WeeklyReviewMessageFormatter as F,
)
from app.domain.entities.adherence_report import ADHERENCE_FALLING, ADHERENCE_RISING


def _weeks(*pairs):

    return [SimpleNamespace(done=d, planned=p, rate=d / p if p else 0.0) for d, p in pairs]


def test_tendencia_vem_da_serie_que_o_atleta_ve():

    # Hélio 15/11: 3/3 · 3/3 · 2/3 · 1/3 era "vem cumprindo mais 👏"
    assert F.shown_direction(_weeks((3, 3), (3, 3), (2, 3), (1, 3))) == ADHERENCE_FALLING

    assert F.shown_direction(_weeks((1, 3), (1, 3), (3, 3), (3, 3))) == ADHERENCE_RISING

    assert F.shown_direction(_weeks((3, 3), (3, 3), (3, 3), (3, 3))) is None

    assert F.shown_direction(_weeks((2, 3), (2, 3), (3, 3), (2, 3))) is None

    assert F.shown_direction(_weeks((3, 3))) is None


def _report(weeks):

    return SimpleNamespace(
        has_series=True, weeks=weeks, trend=ADHERENCE_RISING,
        missed_day=None, missed_type=None,
    )


def test_hello_case_nao_celebra_e_avisa_que_caiu():

    lines = F._adherence_lines(_report(_weeks((3, 3), (3, 3), (2, 3), (1, 3))))

    text = "\n".join(lines)

    assert "cumprindo mais" not in text

    assert "vem caindo" in text


def test_sequencia_cumprida_nao_vem_junto_de_vem_caindo():

    # Renato 15/11: "2 semanas SEGUIDAS cumprindo" + "o cumprimento vem caindo"
    lines = F._adherence_lines(_report(_weeks((3, 3), (3, 3), (2, 2), (2, 2))))

    text = "\n".join(lines)

    assert "SEGUIDAS" in text

    assert "vem caindo" not in text


def test_volume_conta_a_semana_zerada():

    # João 15/11: semana de 0 km com "Volume: subindo (+20,6%)"
    trend = EvolutionAnalyzer._trend([10, 10, 10, 10, 12, 14, 12, 0], zero_counts=True)

    assert trend["direction"] != "up"

    # pace: zero é "sem dado" e segue fora
    assert EvolutionAnalyzer._trend([6, 6, 6, 6, 6, 6, 6, 0])["delta_percent"] == 0.0


def test_retrato_nao_fala_em_progredir_com_semana_furada():

    state = "Teu corpo está absorvendo bem o treino E a forma vem subindo — a janela ideal pra progredir."

    text = StatePortraitWriter.with_week_reality(state, {"done": 1, "planned": 3})

    assert "progredir" not in text

    assert "1 de 3 treinos" in text

    assert StatePortraitWriter.with_week_reality(state, {"done": 2, "planned": 3}) == state

    assert StatePortraitWriter.with_week_reality(state, None) == state

    other = "Você vem evoluindo, mas a recuperação deu uma caída."

    assert StatePortraitWriter.with_week_reality(other, {"done": 0, "planned": 3}) == other
