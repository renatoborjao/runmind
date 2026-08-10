from datetime import date, timedelta

from app.application.history.silence_detector import SilenceDetector


def _runs(today: date, days_ago: list[int]) -> list[date]:

    return [today - timedelta(days=d) for d in days_ago]


TODAY = date(2026, 8, 10)


def test_recently_active_is_not_dark():
    """Correu ontem — longe de silêncio."""

    runs = _runs(TODAY, [1, 3, 5, 8, 10, 12])

    v = SilenceDetector.assess(runs, None, TODAY)

    assert not v.is_dark
    assert v.days_silent == 1


def test_three_times_a_week_silent_eight_days_is_dark():
    """Padrão ~3x/semana (gaps ~2-3d) sumido há 8 dias → notícia."""

    # corridas a cada ~2-3 dias, a última há 8 dias
    runs = _runs(TODAY, [8, 10, 13, 15, 17, 20])

    v = SilenceDetector.assess(runs, None, TODAY)

    assert v.is_dark
    assert v.days_silent == 8
    assert v.threshold_days == 6  # piso (gap pequeno * 2.5, mas clampa em 6)


def test_once_a_week_athlete_not_dark_at_eight_days():
    """Quem corre ~1x/semana (gaps 7d) sumido há 8 dias NÃO é silêncio — o
    limiar acompanha o padrão dele (não um número fixo)."""

    runs = _runs(TODAY, [8, 15, 22, 29])

    v = SilenceDetector.assess(runs, None, TODAY)

    assert not v.is_dark
    assert v.threshold_days == 14  # 7 * 2.5 = 17.5 -> teto 14


def test_once_a_week_athlete_dark_after_fifteen_days():

    runs = _runs(TODAY, [15, 22, 29, 36])

    v = SilenceDetector.assess(runs, None, TODAY)

    assert v.is_dark
    assert v.days_silent == 15


def test_conversation_keeps_athlete_from_being_dark():
    """Sem treino há 9 dias, MAS mandou mensagem ontem → engajado, não é
    silêncio (o gatilho é sumir dos DOIS: treino e conversa)."""

    runs = _runs(TODAY, [9, 11, 13, 16])

    v = SilenceDetector.assess(runs, TODAY - timedelta(days=1), TODAY)

    assert not v.is_dark
    assert v.last_active == TODAY - timedelta(days=1)
    assert v.days_silent == 1


def test_never_started_is_not_dark():
    """Sem nenhuma corrida — é onboarding, não re-engajamento."""

    v = SilenceDetector.assess([], None, TODAY)

    assert not v.is_dark
    assert v.last_active is None


def test_episode_key_tracks_last_sign_of_life():
    """A chave do episódio = último sinal de vida → muda quando o atleta
    volta, liberando um novo toque no futuro (e travando a repetição agora)."""

    runs = _runs(TODAY, [8, 10, 13])

    v = SilenceDetector.assess(runs, None, TODAY)

    assert v.episode_key == (TODAY - timedelta(days=8)).isoformat()

    # depois de voltar a treinar, o episódio é OUTRO
    runs2 = _runs(TODAY, [1, 8, 10, 13])

    v2 = SilenceDetector.assess(runs2, None, TODAY)

    assert v2.episode_key != v.episode_key
    assert not v2.is_dark
