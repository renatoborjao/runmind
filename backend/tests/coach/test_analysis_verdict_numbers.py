"""O veredito da análise em números já contados (revisão de conversas 17/11): o que o atleta FEZ
× o que CORTOU, os km acima do teto que a média esconde, e o pace fora da faixa estrita mesmo
quando o pareamento aceitou pela folga."""

from types import SimpleNamespace

from app.application.coach.writer.ai_analysis_writer import AIAnalysisWriter as W


def test_volume_separa_o_que_fez_do_que_cortou():

    assert W.volume_numbers(16, 7.0) == (
        "Volume: fez 7,0 de 16,0 km = 44% do planejado (cortou 56%)"
    )

    assert W.volume_numbers(10, 12.5) == (
        "Volume: fez 12,5 de 10,0 km = 125% do planejado (25% acima)"
    )


def test_volume_dentro_de_10_por_cento_ou_sem_plano_nao_vira_fato():

    assert W.volume_numbers(10, 9.3) is None

    assert W.volume_numbers(None, 7) is None

    assert W.volume_numbers(10, 0) is None


def test_teto_lista_os_km_acima_mesmo_com_media_abaixo():

    line = W.ceiling_numbers([138, 140, 141, 143, 145, 142, 139], 144, 150)

    assert line == "Teto aeróbico (144 bpm): 1 de 7 km ACIMA dele (km 5: 145); FC máxima 150"


def test_teto_respeitado_diz_isso_e_aponta_so_o_pico():

    assert W.ceiling_numbers([130, None, 135], 144, 149) == (
        "Teto aeróbico (144 bpm): todos os 2 km com FC abaixo dele (só o pico foi a 149)"
    )

    assert W.ceiling_numbers([150], None) is None

    assert W.ceiling_numbers([None, None], 144) is None


def test_tempo_em_z4_ou_acima():

    assert W.high_zone_share([10, 20, 13, 50, 7]) == 57

    assert W.high_zone_share([0, 0, 0, 0, 0]) is None

    assert W.high_zone_share(None) is None


def test_pace_fora_da_faixa_estrita():

    assert W.pace_outside_range(5 + 47 / 60, "5:30", "5:45") == "2 s mais lento"

    assert W.pace_outside_range(5 + 25 / 60, "5:30", "5:45") == "5 s mais rápido"

    assert W.pace_outside_range(5 + 35 / 60, "5:45", "5:30") is None

    assert W.pace_outside_range(None, "5:30", "5:45") is None

    assert W.pace_outside_range(5.5, "x", "5:45") is None


def _block(pace, within=True):

    return SimpleNamespace(
        label="Bloco principal", executed_distance_m=5000, executed_duration_sec=1735,
        executed_pace=pace, executed_hr=None, pace_min="5:30", pace_max="5:45",
        planned_distance_m=None, planned_duration_sec=None, within_target=within, kind="run",
    )


def test_bloco_aceito_pela_folga_nao_vira_dentro_da_faixa():

    comparison = SimpleNamespace(blocks=[_block(5 + 47 / 60)], missing=[])

    fact = W._block_comparison_fact(comparison)

    assert "2 s mais lento da faixa" in fact

    assert "NÃO diga 'dentro da faixa'" in fact

    assert "[pace dentro do alvo]" not in fact


def test_bloco_dentro_da_faixa_estrita_segue_igual():

    comparison = SimpleNamespace(blocks=[_block(5 + 38 / 60)], missing=[])

    assert "[pace dentro do alvo]" in W._block_comparison_fact(comparison)
