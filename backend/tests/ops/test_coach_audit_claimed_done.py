"""A auditoria pega "o coach disse que já está certo, sem agir". Caso REAL —
Leonardo, 18/10 19:08: pediu "ajustar o nome dela na aba treino" e o coach
respondeu "A prova já está certinha no teu cadastro" sem nenhuma ação; a lista de
provas seguia "Corrida 10km/15km"."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[3] / "ops" / "coach_audit.py"

_spec = importlib.util.spec_from_file_location("coach_audit_claimed_done", _PATH)

audit = importlib.util.module_from_spec(_spec)

_spec.loader.exec_module(audit)

LEONARDO_ASKS = (
    "A corrida do dia 20/12/26 é de 10km, nao 10/15km, ajustar o nome dela na aba "
    "treino"
)

LEONARDO_GOT = (
    "A prova já está certinha no teu cadastro como 10 km na TF Sports Villa Lobos "
    "III no dia 20/12/2026, Leonardo!"
)


def test_the_real_leonardo_case_is_flagged():

    assert audit.claimed_done_without_action(LEONARDO_ASKS, LEONARDO_GOT, [])
    assert audit.claimed_done_without_action(LEONARDO_ASKS, LEONARDO_GOT, None)


def test_an_action_means_the_coach_did_something():

    goal = [{"type": "goal", "scope": "single_session"}]

    assert not audit.claimed_done_without_action(LEONARDO_ASKS, LEONARDO_GOT, goal)


def test_no_request_no_flag():
    """Conversa comum: o coach confirma algo que ELE sabe, sem que o atleta tenha
    pedido mudança nenhuma."""

    assert not audit.claimed_done_without_action(
        "Qual é a minha prova?", LEONARDO_GOT, [],
    )


def test_a_request_without_a_done_claim_is_not_flagged():

    assert not audit.claimed_done_without_action(
        LEONARDO_ASKS, "Boa, Leonardo! Me conta qual nome você quer na lista?", [],
    )


def test_empty_values_never_raise():

    assert not audit.claimed_done_without_action("", "", [])
    assert not audit.claimed_done_without_action(None, None, None)
