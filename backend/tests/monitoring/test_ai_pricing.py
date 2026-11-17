from datetime import date

from app.application.monitoring.ai_pricing import cost_brl, price, record_cost_brl


def test_pro_no_preco_oficial_e_lote_pela_metade():

    full = cost_brl("gemini-3.1-pro-preview", 1_000_000, 1_000_000)

    assert round(full, 2) == round((2.0 + 12.0) * 5.40, 2)

    assert round(cost_brl("gemini-3.1-pro-preview", 1_000_000, 1_000_000, batch=True), 2) == round(full / 2, 2)


def test_flash_dobra_em_2027():

    assert price("gemini-3.6-flash", date(2026, 12, 31)) == (0.75, 3.75)

    assert price("gemini-3.6-flash", date(2027, 1, 1)) == (1.50, 7.50)

    assert price("gemini-3.5-flash-lite", date(2027, 6, 1)) == (0.30, 2.50)


def test_registro_do_medidor_conta_raciocinio_como_saida_e_modelo_desconhecido_tem_padrao():

    rec = {"ts": "2026-11-15T23:00:59+00:00", "model": "gemini-3.6-flash",
           "in": 1_000_000, "out": 500_000, "thoughts": 500_000}

    assert round(record_cost_brl(rec), 2) == round((0.75 + 3.75) * 5.40, 2)

    assert record_cost_brl({"model": "novo", "in": 0, "out": 0}) == 0
