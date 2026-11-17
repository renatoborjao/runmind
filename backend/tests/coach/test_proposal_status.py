from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.application.coach.conversation.proposal_status import (
    OPEN,
    UNANSWERED,
    describe_operations,
    dossier_lines,
    message_with_changes,
    status,
)

BRT = ZoneInfo("America/Sao_Paulo")

NOW = datetime(2026, 11, 15, 6, 55, tzinfo=BRT)

OPS = [
    {"action": "replace", "day": "Sunday",
     "session": {"workout_type": "Longão", "planned_distance_km": 12.0}},
    {"action": "drop", "day": "Wednesday"},
    {"action": "replace", "day": "Friday",
     "session": {"workout_type": "Limiar Intervalado", "planned_duration_minutes": 40}},
]


def _proposal(hours_ago, ops=OPS):

    return {
        "kind": "missed", "week_start": "2026-11-09",
        "preview": "Prefiro reduzir o longão de amanhã para 12 km leves. Posso aplicar?",
        "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
        "operations": ops,
    }


def test_status_aberta_sem_resposta_e_velha():

    assert status(_proposal(1), NOW) == OPEN

    assert status(_proposal(25), NOW) == UNANSWERED

    assert status(_proposal(80), NOW) is None

    assert status(None, NOW) is None

    assert status({"created_at": "lixo"}, NOW) is None


def test_status_aceita_data_sem_fuso_como_hora_local():

    naive = (NOW - timedelta(hours=2)).replace(tzinfo=None).isoformat()

    assert status({"created_at": naive}, NOW) == OPEN


def test_operacoes_em_portugues_de_corredor():

    assert describe_operations(OPS) == [
        "domingo: Longão 12 km",
        "quarta-feira: sai do plano (descanso)",
        "sexta-feira: Limiar Intervalado 40 min",
    ]

    assert describe_operations(None) == []


def test_mensagem_ganha_o_que_muda_e_como_responder():

    text = message_with_changes("Reorganizei os dias. Posso aplicar?", OPS[:1])

    assert text.startswith("Reorganizei os dias. Posso aplicar?\n\n👉 O que muda, se você topar:")

    assert "• domingo: Longão 12 km" in text

    assert "*sim*" in text

    assert message_with_changes("Segue igual.", []) == "Segue igual."


def test_dossie_avisa_proposta_aberta_sem_contradizer():

    lines = dossier_lines(_proposal(1), NOW)

    assert lines[0].startswith("PROPOSTA EM ABERTO (você propôs em 15/11 05:55")

    assert "para a semana de 09/11 — domingo: Longão 12 km" in lines[0]

    assert "NÃO contradiga" in lines[0]


def test_dossie_lembra_proposta_que_caducou_sem_resposta():

    lines = dossier_lines(_proposal(25), NOW)

    assert lines[0].startswith("PROPOSTA SEM RESPOSTA")

    assert "Não celebre nem cobre o treino antigo" in lines[0]

    assert dossier_lines(_proposal(80), NOW) == []
