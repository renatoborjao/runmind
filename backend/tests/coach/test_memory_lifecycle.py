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


# ------------------------------------------------- ausência com FIM (29/09)

PAUSA = (
    "Vai se ausentar dos treinos por 7 dias devido à remoção de pintas "
    "(proibido fazer atividade física no período)."
)
CRIADO = "2026-09-29T15:21:19-03:00"


def test_absence_by_duration_has_an_end():
    """A pausa médica do Renato virou memória ETERNA: 'por 7 dias' não era
    reconhecido como janela e disponibilidade é durável."""
    exp = MemoryLifecycle.expiry_for("disponibilidade", PAUSA, CRIADO)
    assert exp == "2026-10-05"  # 29/09 + 7 dias, inclusive


def test_explicit_until_from_the_extraction_wins():
    exp = MemoryLifecycle.expiry_for(
        "disponibilidade", "Sem treinar de 29/09 a 05/10", CRIADO,
        until="2026-10-05",
    )
    assert exp == "2026-10-05"


def test_absurd_until_is_ignored_and_the_net_takes_over():
    for bad in ("2020-01-01", "2031-01-01", "amanhã", ""):
        assert MemoryLifecycle.expiry_for(
            "disponibilidade", PAUSA, CRIADO, until=bad,
        ) == "2026-10-05"


def test_absence_until_a_date_or_weekday():
    assert MemoryLifecycle.expiry_for(
        "disponibilidade", "Viaja até 12/10, sem correr", CRIADO,
    ) == "2026-10-12"

    # terça 29/09 -> "até sexta" = 02/10
    assert MemoryLifecycle.expiry_for(
        "disponibilidade", "Ausente até sexta", CRIADO,
    ) == "2026-10-02"


def test_absence_duration_counts_from_the_cited_start():
    assert MemoryLifecycle.expiry_for(
        "disponibilidade", "Ausente a partir de 05/10 por 2 semanas", CRIADO,
    ) == "2026-10-18"


def test_trip_and_word_numbers():
    assert MemoryLifecycle.expiry_for(
        "vida", "Viagem de trabalho, dez dias fora", CRIADO,
    ) == "2026-10-08"


def test_routine_with_days_is_not_an_absence():
    """'3 dias por semana' e 'até 50 min' são rotina durável, não pausa."""
    for text in ("Treina 3 dias por semana pela manhã", "Prefere treinos de até 50 min"):
        assert MemoryLifecycle.expiry_for("disponibilidade", text, CRIADO) is None


def test_injury_is_never_expired_by_the_net():
    assert MemoryLifecycle.expiry_for(
        "lesao", "Dor no joelho, precisa parar por 2 semanas", CRIADO,
    ) is None


def test_is_absence_cues_and_categories():
    assert MemoryLifecycle.is_absence("disponibilidade", PAUSA) is True
    assert MemoryLifecycle.is_absence("preferencia", PAUSA) is False
    assert MemoryLifecycle.is_absence("disponibilidade", "Prefere correr de manhã") is False


def test_legacy_absence_without_expires_at_expires_by_derivation():
    legacy = _entry("disponibilidade", PAUSA, CRIADO)
    assert MemoryLifecycle.is_expired(legacy, date(2026, 10, 5)) is False
    assert MemoryLifecycle.is_expired(legacy, date(2026, 10, 6)) is True
