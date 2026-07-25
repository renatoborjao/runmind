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


# ---------------- extractor parse (validação) ----------------


def test_parse_keeps_only_valid_scales():

    data = CheckinExtractor._parse(
        '{"energy": 2, "sleep_quality": 5, "soreness": 9, "note": "perna"}'
    )

    assert data["energy"] == 2
    assert data["sleep_quality"] == 5
    assert data["soreness"] is None      # 9 fora de 1-5 -> descartado
    assert data["note"] == "perna"


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
