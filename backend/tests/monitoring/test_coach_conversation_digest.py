from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.application.monitoring.coach_conversation_digest import (
    MAX_ITEM_CHARS,
    collect,
    parse_ts,
    proposal_lines,
    render,
)

SINCE = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)  # ter 10/11 00:00 BRT

BRT = ZoneInfo("America/Sao_Paulo")


def test_parse_ts_aceita_sem_fuso_como_utc_e_recusa_lixo():

    assert parse_ts("2026-11-10T12:00:00") == datetime(2026, 11, 10, 12, tzinfo=UTC)

    assert parse_ts("2026-11-10T12:00:00Z") == datetime(2026, 11, 10, 12, tzinfo=UTC)

    assert parse_ts("ontem") is None

    assert parse_ts(None) is None


def test_janela_compara_datas_de_verdade_entre_fusos():

    chat = [
        # 23:30 BRT do dia 09 = 02:30 UTC do 10: ANTES da janela, mesmo com a string "maior"
        {"role": "user", "text": "fora", "timestamp": "2026-11-09T23:30:00-03:00"},
        {"role": "user", "text": "dentro", "timestamp": "2026-11-10T00:30:00-03:00"},
    ]

    items = collect(SINCE, chat=chat)

    assert [i.text for i in items] == ["dentro"]


def test_junta_tudo_em_ordem_e_nao_repete_proativo_que_esta_no_chat():

    items = collect(
        SINCE,
        chat=[
            {"role": "user", "text": "como foi meu treino?", "timestamp": "2026-11-11T10:00:00+00:00"},
            {"role": "assistant", "text": "Bom dia!  Hoje é leve.", "timestamp": "2026-11-11T09:00:00+00:00"},
        ],
        outbox=[
            {"text": "Bom dia! Hoje é leve.", "timestamp": "2026-11-11T09:00:01+00:00"},
            {"text": "Lembrete do longão", "timestamp": "2026-11-12T09:00:00+00:00"},
        ],
        analyses={
            "1": {"date": "2026-11-11", "workout_type": "easy", "distance_km": 6.04,
                  "analysis": "Ritmo controlado.", "created_at": "2026-11-11T11:00:00+00:00"},
            "0": {"date": "2026-11-01", "analysis": "velha", "created_at": "2026-11-01T11:00:00+00:00"},
        },
        brain_log=[
            {"ts": "2026-11-11T10:00:05+00:00", "incoming": "x", "say": "ok", "fallback": False, "pending": False},
            {"ts": "2026-11-11T10:00:06+00:00", "incoming": "muda meu longão", "say": "anotado",
             "fallback": True, "pending": False},
        ],
        memories=[
            {"category": "preference", "status": "active", "content": "longão no sábado",
             "created_at": "2026-11-11T10:01:00+00:00"},
        ],
    )

    assert [i.kind for i in items] == [
        "coach",
        "atleta",
        "cérebro: plano B (fallback)",
        "memória gravada (preference, active)",
        "análise do treino (2026-11-11 · easy · 6.0 km)",
        "coach (proativo)",
    ]

    assert "muda meu longão" in items[2].text


def test_render_mostra_hora_local_plano_e_corta_texto_longo():

    items = collect(
        SINCE,
        chat=[{"role": "assistant", "text": "a" * (MAX_ITEM_CHARS + 50),
               "timestamp": "2026-11-16T23:21:00+00:00"}],
    )

    text = render("Ana", items, ["Terça — easy · 6 km"], BRT, 7)

    assert "===== Ana — últimos 7 dias (0 mensagem(ns) do atleta, 1 registro(s)) =====" in text

    assert "[seg 16/11 20:21] coach:" in text

    assert "Terça — easy · 6 km" in text

    assert "cortado:" in text


def test_render_sem_nada_na_janela():

    text = render("Ana", [], [], BRT, 3)

    assert "(sem plano gravado)" in text

    assert "(nada na janela)" in text


def test_proativo_repetido_no_arquivo_e_na_janela_aparece_uma_vez_so_se_nao_estiver_no_chat():

    outbox = [
        {"text": "Lembrete A", "timestamp": "2026-11-11T09:00:00+00:00"},
        {"text": "Lembrete B", "timestamp": "2026-11-12T09:00:00+00:00"},
    ]

    items = collect(SINCE, outbox=outbox)

    assert [i.text for i in items] == ["Lembrete A", "Lembrete B"]


def test_cerebro_com_proposta_em_aberto_tem_rotulo_claro():

    items = collect(
        SINCE,
        brain_log=[{"ts": "2026-11-11T10:00:00+00:00", "incoming": "sim", "say": "aplicado",
                    "fallback": False, "pending": True}],
    )

    assert items[0].kind == "cérebro: chegou com proposta do coach em aberto"


def test_proposta_pendente_vira_linhas_e_aparece_no_bloco():

    proposal = {
        "kind": "move", "week_start": "2026-11-16",
        "operations": [
            {"action": "drop", "day": "Wednesday"},
            {"action": "replace", "day": "Friday",
             "session": {"workout_type": "intervals", "planned_distance_km": 8}},
        ],
    }

    lines = proposal_lines(proposal)

    assert lines == [
        "tipo move · semana 2026-11-16",
        "drop Wednesday",
        "replace Friday: intervals · 8 km",
    ]

    text = render("Ana", [], [], BRT, 7, pending=lines)

    assert "-- proposta em aberto (espera o sim do atleta) --" in text

    assert "replace Friday: intervals · 8 km" in text

    assert proposal_lines(None) == []
