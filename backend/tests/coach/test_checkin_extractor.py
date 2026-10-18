from app.application.coach.intelligence.checkin_extractor import (
    CheckinDetector,
    CheckinExtractor,
)
from app.application.coach.intelligence.checkin_service import CheckinService
from app.domain.entities.daily_checkin import DailyCheckin

# ---------------- detector (portão barato) ----------------


def test_detector_catches_feeling_statements():

    assert CheckinDetector.mentions_state("dormi mal essa noite")
    assert CheckinDetector.mentions_state("tô meio detonado hoje")
    assert CheckinDetector.mentions_state("minha panturrilha tá doendo")
    assert CheckinDetector.mentions_state("acordei inteiro, cheio de energia")


def test_detector_ignores_unrelated_messages():

    assert not CheckinDetector.mentions_state("qual meu próximo treino?")
    assert not CheckinDetector.mentions_state("valeu, coach 💪")


def test_detector_catches_illness():
    """O gap do Renato: 'tô gripado' precisa disparar a captura."""

    assert CheckinDetector.mentions_state("tô gripado hoje")
    assert CheckinDetector.mentions_state("acordei com febre")
    assert CheckinDetector.mentions_state("peguei um resfriado")
    assert CheckinDetector.mentions_state("tô doente, uma virose")


# ---------------- extractor parse (validação) ----------------


def test_parse_keeps_only_valid_scales():

    data = CheckinExtractor._parse(
        '{"energy": 2, "sleep_quality": 5, "soreness": 9, "note": "perna"}'
    )

    assert data["energy"] == 2
    assert data["sleep_quality"] == 5
    assert data["soreness"] is None      # 9 fora de 1-5 -> descartado
    assert data["note"] == "perna"
    assert data["illness"] is False      # ausente -> false


def test_parse_captures_illness_flag():

    data = CheckinExtractor._parse(
        '{"energy": null, "sleep_quality": null, "soreness": null, '
        '"illness": true, "note": "gripe com dor de garganta"}'
    )

    assert data["illness"] is True
    assert data["note"] == "gripe com dor de garganta"


def test_parse_rejects_booleans_and_garbage():

    data = CheckinExtractor._parse(
        '{"energy": true, "sleep_quality": "boa", "note": 123}'
    )

    assert data["energy"] is None
    assert data["sleep_quality"] is None
    assert data["note"] == ""


def test_parse_invalid_json_is_none():

    assert CheckinExtractor._parse("não é json") is None


# ---------------- service render ----------------


def test_render_turns_scales_into_words():

    checkin = DailyCheckin(
        day="2026-07-25", at="2026-07-25T08:00:00",
        energy=1, sleep_quality=2, soreness=4, note="panturrilha direita",
    )

    rendered = CheckinService.render(checkin)

    assert "energia exausto" in rendered
    assert "sono ruim" in rendered
    assert "dor considerável" in rendered
    assert "panturrilha direita" in rendered
    assert "dose" in rendered            # deixa claro pra IA que é pra dosar


def test_render_empty_checkin_is_blank():

    checkin = DailyCheckin(day="2026-07-25", at="2026-07-25T08:00:00")

    assert CheckinService.render(checkin) == ""


# ---------------- recuperação: a doença que PASSOU (caso renato2) ----------------


def test_detector_catches_the_recovery_statements_that_used_to_slip_by():
    """'Não tem mais infecção amigo' (18/10) não tinha NENHUMA palavra do portão:
    nunca chegou ao extrator, e a gripe seguia em aberto."""

    assert CheckinDetector.mentions_state("Não tem mais infecção amigo")
    assert CheckinDetector.mentions_state("tô recuperado, bora")
    assert CheckinDetector.mentions_state("já sarei")


def test_parse_reads_the_recovered_flag():

    data = CheckinExtractor._parse(
        '{"energy": 5, "sleep_quality": null, "soreness": null, '
        '"illness": false, "recovered": true, "note": "recuperado da gripe"}'
    )

    assert data["recovered"] is True and data["illness"] is False


def test_recovery_beats_illness_when_the_model_marks_both():
    """'mesmo voltando da gripe me senti inteiro' (17/10) saiu illness=true e
    reabriu a doença. Passou e doente não convivem: a recuperação vence."""

    data = CheckinExtractor._parse(
        '{"energy": 5, "illness": true, "recovered": true, "note": ""}'
    )

    assert data["illness"] is False and data["recovered"] is True


def test_parse_recovered_defaults_to_false():

    assert CheckinExtractor._parse('{"energy": 2}')["recovered"] is False


def test_render_tells_the_coach_he_is_recovered_not_sick():

    ok = CheckinService.render(DailyCheckin(
        day="2026-10-18", at="2026-10-18T09:00:00", recovered=True,
    ))

    assert "PASSOU" in ok and "recuperado" in ok and "DOENTE" not in ok

    sick = CheckinService.render(DailyCheckin(
        day="2026-10-18", at="2026-10-18T09:00:00", illness=True,
    ))

    assert "DOENTE" in sick
