"""Governador de mensagens PROATIVAS: o portão único por onde passa tudo que o
coach INICIA (briefing, review/plano, companheiro de prova, re-engajamento,
recap, empurrões de progresso...).

POR QUE EXISTE: eram ~8 notificadores independentes, cada um com sua trava e
horário, sem ninguém enxergando o conjunto — daí a família de bugs de proativo
repetido/fora de hora e o risco de EMPILHAR mensagens no mesmo dia. O portão dá,
numa camada de POLÍTICA transversal:
- DIÁRIO unificado (o que o coach já disse hoje) — fonte única e observável;
- ORÇAMENTO diário (teto de proativos/dia) com ISENÇÃO dos ESSENCIAIS;
- DEDUP por conteúdo (pega repetição idêntica entre fontes distintas).

NÃO substitui a lógica de domínio de cada notificador (é hora local? tem prova?);
ela continua decidindo O QUE dizer. O governador só decide SE pode sair agora.
Resposta REATIVA no chat NÃO passa por aqui. Ver [[project_governador_proativos]]
e [[feedback_orientar_nao_mandar]]."""

import hashlib

from app.core.clock import today_local
from app.infrastructure.integrations.telegram.telegram_text import to_plain_text
from app.infrastructure.persistence.proactive_ledger_repository import (
    ProactiveLedgerRepository,
)

# --- TIERS de prioridade (maior = mais importante) ---
# A regra do teto separa ESSENCIAL de EXTRA:
# - ESSENCIAL (tier >= HIGH): resposta a um EVENTO do atleta (correu, bateu
#   recorde), beat emocional (dia da prova) e as ÂNCORAS agendadas que o atleta
#   ESPERA (briefing diário, review/plano de domingo, follow-up de saúde).
#   SEMPRE saem (só deduplicados) — segurar um desses é pior que qualquer
#   excesso.
# - EXTRA (tier <= NORMAL): o coach se VOLUNTARIANDO com comentário a mais
#   (empurrão de pace/cadência, retrato, projeção de meta, avisos informativos
#   de prova, re-engajamento, recap). É o risco REAL de spam — então dividem o
#   teto diário (Renato: 2/dia) e CEDEM em dia cheio.
CRITICAL = 3   # evento/emocional
HIGH = 2       # âncora agendada esperada
NORMAL = 1     # extra útil
LOW = 0        # extra nice-to-have

# kind -> tier. Kind desconhecido cai em HIGH (conservador a favor de ENVIAR na
# dúvida — nunca engolir algo por falta de etiqueta).
_TIERS = {
    # ESSENCIAIS — evento/emocional (sempre saem, isentos do teto)
    "feedback": CRITICAL,          # análise pós-treino: ele acabou de correr
    "race_debrief": CRITICAL,      # debrief da prova cumprida
    "personal_record": CRITICAL,   # recorde batido
    "race_day": CRITICAL,          # manhã da prova
    "race_eve": CRITICAL,          # véspera
    "race_journey": CRITICAL,      # recap da jornada (3 dias antes)
    "announcement": CRITICAL,      # informativo do dono (broadcast)
    # ESSENCIAIS — âncoras agendadas esperadas (sempre saem, isentas do teto)
    "morning_briefing": HIGH,
    "weekly_review": HIGH,
    "weekly_plan": HIGH,
    "wellbeing_followup": HIGH,
    # EXTRAS — dividem o teto diário e cedem em dia cheio
    "race_week": NORMAL,
    "race_taper": NORMAL,
    "reengagement": NORMAL,
    "goal_projection": NORMAL,
    "monthly_recap": LOW,
    "pace_progress": LOW,
    "cadence_progress": LOW,
    "state_portrait": LOW,
}


def tier_for(kind: str) -> int:

    return _TIERS.get(kind, HIGH)


def _hash(message: str) -> str:
    """Hash do conteúdo (texto puro, sem markdown) pra dedup entre fontes."""

    return hashlib.sha256(
        to_plain_text(message or "").strip().encode("utf-8")
    ).hexdigest()


class ProactiveGovernor:

    @staticmethod
    def admit(profile: str, kind: str, message: str, budget: int) -> tuple[bool, str]:
        """Pode sair agora? Devolve (ok, motivo). Regras, em ordem:
        1) DEDUP: conteúdo idêntico já enviado HOJE -> nega.
        2) ESSENCIAL (tier >= HIGH): sempre passa (isento do teto).
        3) TETO: os EXTRAS (tier <= NORMAL) compartilham `budget` envios/dia; ao
           encher, nega (o notificador fica em silêncio hoje — nunca vira erro)."""

        tier = tier_for(kind)

        day = today_local().isoformat()

        ledger = ProactiveLedgerRepository()

        today = ledger.today(profile, day)

        content_hash = _hash(message)

        if any(e.get("hash") == content_hash for e in today):

            return False, "duplicate"

        if tier >= HIGH:

            return True, "essential"

        # o teto vale só pros EXTRAS (tier < HIGH); essenciais não ocupam vaga
        used = sum(1 for e in today if e.get("tier", HIGH) < HIGH)

        if used < budget:

            return True, f"within_budget({used + 1}/{budget})"

        return False, f"budget_full({used}/{budget})"

    @staticmethod
    def record(profile: str, kind: str, message: str) -> None:
        """Registra o envio no diário (best-effort — nunca derruba o envio)."""

        try:

            ProactiveLedgerRepository().append(
                profile,
                kind=kind,
                tier=tier_for(kind),
                day_iso=today_local().isoformat(),
                content_hash=_hash(message),
            )

        except Exception as e:

            print(f"Falha ao registrar proativo no diário ({profile}): {e}")
