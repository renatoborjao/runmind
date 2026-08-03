from app.application.coach.intelligence.prehab_advisor import PrehabAdvisor


def test_detects_knee_area():

    found = PrehabAdvisor.detect_area("tô com o joelho doendo depois do treino")

    assert found is not None
    label, exercises = found
    assert "joelho" in label
    assert len(exercises) >= 2


def test_detects_calf_without_accent():

    found = PrehabAdvisor.detect_area("dor na panturrilha")

    assert found is not None
    assert "panturrilha" in found[0]


def test_unknown_area_returns_none():

    assert PrehabAdvisor.detect_area("tô meio cansado hoje") is None


def test_directive_for_pain_with_area_has_exercises_and_safety():

    d = PrehabAdvisor.directive_for_pain("meu joelho travou")

    assert "joelho" in d
    assert "glúteo" in d
    assert "profissional" in d  # disclaimer de segurança


def test_directive_for_pain_unknown_asks_where():

    d = PrehabAdvisor.directive_for_pain("tá doendo aqui")

    assert "ONDE" in d
    assert "profissional" in d


def test_directive_for_pain_empty_note():

    assert PrehabAdvisor.directive_for_pain("") == ""


def test_general_directive_is_prevention():

    d = PrehabAdvisor.directive_general()

    assert "PREVEN" in d.upper()
    assert "glúteo" in d
