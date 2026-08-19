"""Governador de proativos: essenciais sempre passam (isentos do teto), os
EXTRAS dividem o teto diário e cedem em dia cheio, e conteúdo idêntico não sai
duas vezes. Inclui o harness do 'dia empilhado' (o pile-up de domingo)."""

from unittest.mock import patch

from app.application.notifications.proactive_governor import (
    HIGH,
    ProactiveGovernor,
    tier_for,
)

MOD = "app.application.notifications.proactive_governor"

BUDGET = 2


class _FakeLedger:
    """Diário em memória compartilhado entre admit/record no teste."""

    def __init__(self):
        self.entries: list[dict] = []

    def today(self, profile, day_iso):
        return [e for e in self.entries if e["day"] == day_iso]

    def append(self, profile, kind, tier, day_iso, content_hash):
        self.entries.append(
            {"kind": kind, "tier": tier, "day": day_iso, "hash": content_hash}
        )


def _run(sequence):
    """Roda uma sequência de (kind, message) por um governador com ledger fake,
    dia fixo. Devolve a lista de (kind, admitido?) — record só quando admitido
    (igual ao CoachOutbox)."""

    ledger = _FakeLedger()
    out = []

    with patch(f"{MOD}.ProactiveLedgerRepository", return_value=ledger):

        for kind, message in sequence:

            ok, _ = ProactiveGovernor.admit("p", kind, message, BUDGET)

            if ok:

                ProactiveGovernor.record("p", kind, message)

            out.append((kind, ok))

    return out


def test_essenciais_sempre_passam_mesmo_com_teto_cheio():

    result = _run([
        ("pace_progress", "a"),      # extra 1
        ("cadence_progress", "b"),   # extra 2 -> teto cheio
        ("morning_briefing", "c"),   # ESSENCIAL -> passa mesmo assim
        ("feedback", "d"),           # ESSENCIAL -> passa
        ("weekly_plan", "e"),        # ESSENCIAL -> passa
    ])

    assert result == [
        ("pace_progress", True),
        ("cadence_progress", True),
        ("morning_briefing", True),
        ("feedback", True),
        ("weekly_plan", True),
    ]


def test_extras_cedem_ao_teto():

    result = _run([
        ("pace_progress", "a"),      # 1/2
        ("reengagement", "b"),       # 2/2
        ("monthly_recap", "c"),      # 3 -> negado
        ("state_portrait", "d"),     # negado
    ])

    assert [ok for _, ok in result] == [True, True, False, False]


def test_essenciais_nao_gastam_o_teto_dos_extras():

    # briefing (essencial) antes NÃO consome vaga: os 2 extras ainda cabem
    result = _run([
        ("morning_briefing", "a"),
        ("pace_progress", "b"),
        ("goal_projection", "c"),
    ])

    assert [ok for _, ok in result] == [True, True, True]


def test_dedup_conteudo_identico_no_mesmo_dia():

    result = _run([
        ("morning_briefing", "bom dia, mesmo texto"),
        ("morning_briefing", "bom dia, mesmo texto"),  # idêntico -> negado
    ])

    assert [ok for _, ok in result] == [True, False]


def test_tier_desconhecido_e_tratado_como_essencial():

    assert tier_for("algo_novo_sem_etiqueta") == HIGH


def test_dia_empilhado_de_domingo():
    """Pile-up real: review + plano (essenciais) SEMPRE saem; os extras de
    domingo (projeção, retrato, pace, cadência) cedem ao teto de 2."""

    result = _run([
        ("weekly_review", "resumo"),        # essencial
        ("goal_projection", "rumo a meta"),  # extra 1/2
        ("state_portrait", "como voce esta"),  # extra 2/2
        ("pace_progress", "mais rapido"),    # extra -> negado
        ("cadence_progress", "cadencia"),    # extra -> negado
        ("weekly_plan", "plano da semana"),  # essencial -> SAI mesmo com teto cheio
    ])

    sent = [kind for kind, ok in result if ok]

    assert "weekly_review" in sent
    assert "weekly_plan" in sent          # o plano nunca é engolido
    assert "goal_projection" in sent
    assert "state_portrait" in sent
    assert "pace_progress" not in sent    # extras além do teto cedem
    assert "cadence_progress" not in sent
