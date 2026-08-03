from app.application.coach.conversation.history_query_detector import (
    HistoryQueryDetector,
)


def test_detects_month_name():

    assert HistoryQueryDetector.looks_historical("como foi meu treino em maio?")
    assert HistoryQueryDetector.looks_historical("quantos km corri em junho")


def test_detects_relative_period():

    assert HistoryQueryDetector.looks_historical("corri mais mês passado?")
    assert HistoryQueryDetector.looks_historical("meu volume este mês")
    assert HistoryQueryDetector.looks_historical("média de km por mês")


def test_detects_count_and_year():

    assert HistoryQueryDetector.looks_historical("quantas corridas fiz")
    assert HistoryQueryDetector.looks_historical("quanto corri em 2025")
    assert HistoryQueryDetector.looks_historical("meu histórico de treinos")


def test_ignores_non_historical():

    assert not HistoryQueryDetector.looks_historical("qual meu treino de hoje?")
    assert not HistoryQueryDetector.looks_historical("como está meu corpo?")
    assert not HistoryQueryDetector.looks_historical("bom dia, tudo certo?")
    assert not HistoryQueryDetector.looks_historical("")
