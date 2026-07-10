from app.application.external_plan.external_plan_extraction_engine import (
    EXTRACTION_PROMPT,
)
from app.application.external_plan.treino_online_legend import (
    internal_type,
    legend_for_prompt,
)


def test_legend_maps_codes_to_names():

    text = legend_for_prompt()

    assert "CCR = Corrida Contínua Rápida" in text
    assert "IT = Intervalado (tiros)" in text
    assert "TR = Trote" in text


def test_internal_type_mapping():

    assert internal_type("IT") == "VO2"
    assert internal_type("CCR") == "TEMPO"
    assert internal_type("CCL") == "EASY"
    assert internal_type("tr") == "RECOVERY"  # case-insensitive
    # não-corrida vira None (ignorado no plano)
    assert internal_type("MUSC") is None
    assert internal_type("NAT") is None


def test_unknown_code_is_none():

    assert internal_type("ZZZ") is None


def test_prompt_placeholder_replaced_without_breaking_json():
    """O prompt tem chaves {} do exemplo JSON; a legenda entra por replace,
    então o exemplo continua intacto."""

    prompt = EXTRACTION_PROMPT.replace("{legend}", legend_for_prompt())

    assert "{legend}" not in prompt
    assert "CCR = Corrida Contínua Rápida" in prompt
    # exemplo JSON preservado
    assert '"sessions"' in prompt
