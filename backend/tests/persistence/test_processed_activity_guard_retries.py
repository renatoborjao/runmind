"""Falha depois da IA não pode reanalisar pra sempre (Hélio, 06/11: 340 análises em 8 h)."""

from app.infrastructure.persistence.processed_activity_guard import ProcessedActivityGuard


def _guard(tmp_path):

    g = ProcessedActivityGuard()
    g.storage = tmp_path
    g.file = tmp_path / "processed_activities.json"

    return g


def test_failed_analysis_is_retried_only_a_few_times(tmp_path):

    g = _guard(tmp_path)

    assert g.check_and_mark(77) is True

    released = []

    for _ in range(6):

        released.append(g.release_for_retry(77))

        if released[-1]:

            assert g.check_and_mark(77) is True  # o poller reprocessa

    assert released == [True, True, True, False, False, False]
    # depois do teto a marca fica: o poller não pega de novo
    assert g.is_marked(77) is True
    assert g.check_and_mark(77) is False


def test_retry_counts_are_per_activity(tmp_path):

    g = _guard(tmp_path)

    for _ in range(3):

        g.check_and_mark(1)
        assert g.release_for_retry(1) is True

    g.check_and_mark(2)
    assert g.release_for_retry(2) is True
