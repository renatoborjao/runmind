from datetime import date
from types import SimpleNamespace

from app.domain.memory_lifecycle import MemoryLifecycle


def _entry(category, content, created_at, expires_at=None):
    return SimpleNamespace(
        category=category, content=content,
        created_at=created_at, expires_at=expires_at, status="active",
    )


# --------------------------------------------------------------- expiração


def test_transient_vida_gets_ttl():
    exp = MemoryLifecycle.expiry_for(
        "vida", "Sintomas de gripe com bastante catarro",
        "2026-08-20T10:00:00-03:00",
    )
    assert exp == "2026-09-03"  # 20/08 + 14 dias


def test_bounded_week_expires_after_the_week():
    exp = MemoryLifecycle.expiry_for(
        "disponibilidade",
        "Trocar terça para quarta referente à semana de 10/08/2026",
        "2026-08-10T10:00:00-03:00",
    )
    assert exp == "2026-08-19"  # 10/08 + 9 dias de folga


def test_start_date_is_durable_not_bounded():
    """'a partir de DD/MM' é INÍCIO, não janela — durável, NÃO expira. Era a
    pegadinha do perfil do Renato (preferência de 50-55min a partir de 03/08)."""
    exp = MemoryLifecycle.expiry_for(
        "preferencia",
        "Treinos de semana até 50-55 min. A partir de 03/08/2026",
        "2026-08-02T10:00:00-03:00",
    )
    assert exp is None


def test_temporary_without_date_gets_short_window():
    exp = MemoryLifecycle.expiry_for(
        "disponibilidade", "Vai treinar em casa temporariamente",
        "2026-08-01T10:00:00-03:00",
    )
    assert exp == "2026-08-11"  # +10 dias


def test_durable_categories_never_expire_by_time():
    for cat in ("preferencia", "objetivo", "motivacao", "disponibilidade"):
        assert MemoryLifecycle.expiry_for(
            cat, "Prefere correr na rua", "2026-07-14T10:00:00-03:00",
        ) is None


def test_outro_is_episodic_with_ttl():
    exp = MemoryLifecycle.expiry_for(
        "outro", "Fez um treino diferente na última sessão",
        "2026-07-15T10:00:00-03:00",
    )
    assert exp == "2026-08-14"  # +30 dias


def test_is_expired_uses_stored_then_derives_for_legacy():
    today = date(2026, 8, 24)

    # legado (sem expires_at): deriva -> semana de 10/08 já venceu
    legacy = _entry(
        "disponibilidade",
        "Trocar treino referente à semana de 10/08/2026",
        "2026-08-10T10:00:00-03:00",
    )
    assert MemoryLifecycle.is_expired(legacy, today) is True

    # durável legado -> nunca vence
    durable = _entry("preferencia", "Corre na rua", "2026-07-14T10:00:00-03:00")
    assert MemoryLifecycle.is_expired(durable, today) is False

    # com expires_at gravado no futuro -> vivo
    future = _entry("vida", "gripe", "2026-08-20T10:00:00-03:00",
                    expires_at="2026-09-03")
    assert MemoryLifecycle.is_expired(future, today) is False


# --------------------------------------------------------------- dedup


def test_near_duplicate_superset():
    assert MemoryLifecycle.is_near_duplicate(
        "Prefere realizar os treinos longos aos domingos.",
        "Prefere realizar os treinos longos aos domingos devido a exames aos "
        "sábados.",
    ) is True


def test_distinct_facts_are_not_duplicates():
    assert MemoryLifecycle.is_near_duplicate(
        "Prefere realizar os treinos na rua",
        "Prefere realizar os treinos longos aos domingos",
    ) is False


def test_short_contents_never_merge():
    assert MemoryLifecycle.is_near_duplicate("Fato 0", "Fato 1") is False


def test_device_synonym_merges_relogio_and_garmin():
    """relógio == Garmin (mesmo aparelho): fatos de 'enviar pro relógio' e
    'enviar pro Garmin' são a mesma coisa."""
    assert MemoryLifecycle.is_near_duplicate(
        "Deseja que os treinos sejam enviados para o relógio",
        "Deseja que os treinos atualizados sejam enviados para o Garmin",
    ) is True
