"""Vigia de prontidão — a ponta que OBSERVA sempre e, atrás de flag, FALA.

Roda no mesmo momento matinal do BodyConductNotifier (09h local), pra ser UMA
voz de manhã, não três. Sempre avalia + grava o diário (observação); só ENVIA
quando `readiness_alerts_enabled` está ligada. Cobre só a LACUNA do ajuste de
corpo: CAUTION (recuperação pedindo atenção num dia puxado) e GREEN (sinal
verde num dia puxado). A sobrecarga real (STRAINED/BRAKE) é tratada pela
proposta do `BodyConductProposer` (também no bom dia do despertar, no dia do
treino), que propõe mudar o plano — aqui não duplicamos.

O texto é determinístico (custo zero, previsível). Dá pra trocar por Gemini
depois, quando o Renato aprovar os alertas no diário. Ver
[[project_analise_corpo_garmin]]."""

from datetime import date

from app.application.coach.intelligence.readiness_service import (
    ReadinessService,
)
from app.application.history.acute_strain_analyzer import (
    AcuteStrainAnalyzer,
    StrainVerdict,
)
from app.core.clock import today_local
from app.core.config import get_settings
from app.domain.entities.readiness_verdict import (
    READINESS_CAUTION,
    READINESS_GREEN,
    ReadinessVerdict,
)
from app.infrastructure.persistence.checkin_repository import CheckinRepository
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)

_ALERT_TIERS = frozenset({READINESS_CAUTION, READINESS_GREEN})

# quantos dias uma doença relatada continua segurando o "pode puxar"
_ILLNESS_WINDOW = 4

# alerta de estresse fisiológico agudo: no máximo 1 a cada N dias (orientar,
# não repetir — o padrão costuma persistir alguns dias)
_STRAIN_COOLDOWN = 5


class ReadinessNotifier:

    @staticmethod
    async def block(profile: str) -> str | None:
        """Bloco de prontidão pra 'bom dia' do despertar: OBSERVA sempre (grava
        o diário — o gate do Renato) e, atrás da flag, DEVOLVE a mensagem
        narrada (ou None). Não envia — quem compõe o briefing junta os blocos.

        None quando: flag desligada, corpo neutro, ou o estado não virou."""

        # avalia + grava o diário SEMPRE (observação) — isto é o gate do Renato
        verdict, entry = await ReadinessService.evaluate(profile)

        # daqui pra baixo é FALA — só com a flag ligada
        if not get_settings().readiness_alerts_enabled:

            return None

        # DOENÇA MANDA: se o atleta avisou que está gripado/resfriado/febril nos
        # últimos dias, isso SUPRIME qualquer "pode puxar" (mesmo com o corpo
        # lendo verde no relógio — o vírus não aparece no HRV). Acolhe e orienta
        # a recuperar; UMA vez por episódio (dedup pela data do relato).
        ill = CheckinRepository().recent_illness(
            profile, today_local().isoformat(), _ILLNESS_WINDOW
        )

        if ill is not None:

            if DispatchGuard.already_sent("readiness_illness", profile, ill.day):

                return None

            DispatchGuard.mark("readiness_illness", profile, ill.day)

            return ReadinessNotifier._illness_message()

        # ESTRESSE FISIOLÓGICO AGUDO: FC-repouso saltou + HRV caiu vs a base do
        # atleta (padrão de overreaching / pré-doença). Também SUPRIME o "pode
        # puxar" e orienta pegar leve — 1x a cada _STRAIN_COOLDOWN dias.
        strain = AcuteStrainAnalyzer.detect(GarminHealthRepository().load(profile))

        if strain.is_strained:

            if not ReadinessNotifier._in_cooldown(
                DispatchGuard.last_key("readiness_strain", profile),
                today_local(),
            ):

                DispatchGuard.mark(
                    "readiness_strain", profile, today_local().isoformat()
                )

                return ReadinessNotifier._strain_message(strain)

            # em cooldown: o alerta agudo não se repete e NUNCA libera o "pode
            # puxar" — mas a conduta do DIA PUXADO (cautela) ainda sai. Antes o
            # cooldown engolia tudo (fartlek do Renato, 22/09, sem aviso).
            if verdict.tier != READINESS_CAUTION:

                return None

        # só a lacuna (CAUTION/GREEN) e só quando é momento NOVO (would_notify:
        # 1º do episódio, piora, ou dia puxado dentro do alerta)
        if verdict.tier not in _ALERT_TIERS or not entry.would_notify:

            return None

        session = await ReadinessNotifier._todays_session(profile)

        return ReadinessNotifier._message(verdict, session)

    @staticmethod
    async def _todays_session(profile: str):
        """Sessão de HOJE (pra a conduta falar DAQUELE treino). Best-effort."""

        try:

            from app.application.planner.current_plan_provider import (
                CurrentPlanProvider,
            )

            _, plan = await CurrentPlanProvider.for_profile(profile)

            today = today_local()

            return next(
                (s for s in plan.sessions if plan.session_date(s) == today),
                None,
            )

        except Exception as e:

            print(f"Sessão de hoje (prontidão) falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    def _in_cooldown(last_key: str | None, today: date) -> bool:
        """True se o alerta de estresse já saiu nos últimos _STRAIN_COOLDOWN
        dias (não repete). Chave inválida/ausente = fora de cooldown."""

        if not last_key:

            return False

        try:

            return (today - date.fromisoformat(last_key)).days < _STRAIN_COOLDOWN

        except ValueError:

            return False

    @staticmethod
    def _strain_message(v: StrainVerdict) -> str:
        """Orientação quando o corpo dá sinal agudo (RHR↑ + HRV↓). Cita os
        números; acolhe e orienta — não diagnostica. Se vier sintoma, médico."""

        return (
            "Bom dia! Teu corpo tá dando um sinal de estresse fisiológico "
            f"incomum: a FC de repouso subiu (~{v.rhr_recent:.0f} vs teu normal "
            f"~{v.rhr_baseline:.0f} bpm) e o HRV caiu abaixo do teu padrão "
            f"(~{v.hrv_recent:.0f} vs ~{v.hrv_baseline:.0f}). Isso costuma "
            "aparecer quando o corpo tá lidando com algo — carga acumulada, "
            "sono curto ou o começo de uma gripe. Hoje vale pegar leve, "
            "caprichar no sono e na hidratação. Se vier sintoma (garganta, "
            "febre, moleza), descansa e procura um médico se precisar. 🤎"
        )

    @staticmethod
    def _illness_message() -> str:
        """Conduta quando o atleta está doente: descanso, sem esforço. Cuidado
        de gente — não é conselho médico; se piorar, procurar um profissional."""

        return (
            "Bom dia! Vi que você não está 100% (gripe/resfriado). Corpo "
            "combatendo infecção + treino puxado não combinam — o esforço pode "
            "arrastar a recuperação. Hoje o melhor treino é DESCANSAR. 🛌\n\n"
            "Quando os sintomas passarem (e sem febre), a gente volta com um "
            "trote bem leve e retoma o ritmo com calma. Se piorar ou bater "
            "febre, procura um médico, tá? Melhoras! 🤎"
        )

    @staticmethod
    def _message(verdict: ReadinessVerdict, session=None) -> str:

        # narra o PORQUÊ: cita os sinais reais na voz do coach, em vez do
        # genérico. Sem sinais capturados, cai num texto ainda humano.
        observed = ReadinessNotifier._join_pt(verdict.signals)

        if verdict.tier == READINESS_CAUTION and session is not None:

            # conduta DO TREINO de hoje (não um "pega leve" genérico): é o que
            # faz a fala do dia puxado ser orientação nova, não repetição
            why = (
                f"teu corpo segue pedindo atenção ({observed})"
                if observed
                else "tua recuperação segue pedindo atenção"
            )

            return (
                f"Bom dia! Hoje é *{session.workout_type}* e {why}. 🩺\n"
                f"👉 Conduta: {ReadinessNotifier._conduct(session)} "
                "Completar bem vale mais que forçar hoje — a decisão é tua. 💪"
            )

        if verdict.tier == READINESS_CAUTION:

            abertura = (
                f"Oi! Reparei que {observed}"
                if observed
                else "Oi! Dei uma olhada no seu corpo hoje e a recuperação "
                "está pedindo atenção"
            )

            return (
                f"{abertura} — por isso hoje, se o treino puxado não render, "
                "pode pegar leve sem culpa. Recuperar bem agora é o que "
                "sustenta a evolução. 💪"
            )

        # GREEN
        abertura = (
            f"Bom dia! {observed[0].upper()}{observed[1:]}, "
            "seu corpo está recuperado e com espaço pra puxar"
            if observed
            else "Bom dia! Seu corpo está recuperado e com espaço pra puxar"
        )

        return (
            f"{abertura} — e hoje o treino pede intensidade. Pode ir com "
            "confiança, o momento está a favor. 🚀"
        )

    @staticmethod
    def _conduct(session) -> str:
        """Como ajustar ESTE tipo de treino puxado com a recuperação em queda."""

        kind = (session.workout_type or "").lower()

        if "longão" in kind or "longao" in kind or "progress" in kind:

            return (
                "faz a parte leve normal e só progride se as pernas "
                "responderem; se a FC subir antes do esperado, fecha em ritmo "
                "leve e, se precisar, encurta uns km."
            )

        if any(k in kind for k in ("simulado", "prova", "teste", "contrarrel")):

            return (
                "com o corpo assim o teste não mede tua forma real — se der, "
                "troca por rodagem e remarca; se for fazer, aquece bem e não "
                "persegue o pace se a FC já vier alta no início."
            )

        if any(k in kind for k in ("subida", "rampa", "morro", "hill")):

            return (
                "sobe por ESFORÇO (não por pace), corta 2–3 repetições se a "
                "descida não trouxer a FC de volta."
            )

        if any(k in kind for k in (
            "tiro", "interval", "fartlek", "vo2", "série", "sprint", "pirâmide",
            "piramide", "escada",
        )):

            return (
                "mantém a estrutura, mas segura os trechos fortes no limite de "
                "BAIXO da faixa; se o 1º bloco já vier pesado, corta 1–2 "
                "repetições."
            )

        if any(k in kind for k in ("limiar", "tempo", "ritmo")):

            return (
                "segura o trecho forte no limite de baixo da faixa e encurta "
                "se a FC disparar."
            )

        return (
            "começa leve e deixa o corpo dizer se dá pra entregar o treino "
            "inteiro; se não vier, reduz a intensidade."
        )

    @staticmethod
    def _join_pt(items: tuple[str, ...]) -> str:
        """Junta frases em pt-BR: 'a', 'a e b', 'a, b e c'."""

        parts = [p for p in items if p]

        if not parts:

            return ""

        if len(parts) == 1:

            return parts[0]

        return f"{', '.join(parts[:-1])} e {parts[-1]}"
