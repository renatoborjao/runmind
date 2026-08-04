"""Loop de CADÊNCIA guiado pela evolução (roda no resumo de domingo).

Cadência é hábito motor: não muda com uma mensagem só, e repetir a cada corrida
cansa. Então o coach ACOMPANHA e reage ao que a cadência está realmente fazendo,
comparando a MEDIANA das corridas recentes (robusta a ruído de ritmo/terreno)
com uma linha de base:

- 1ª vez com cadência baixa  → manda a dica inicial e passa a acompanhar
- subiu de forma sustentada  → reconhece o progresso e re-ancora a base
- bateu o alvo (~170)        → celebra e ENCERRA pra sempre (meta cumprida)
- travou por ~4 semanas      → UM re-cutução com um drill novo, e cala
                               (orienta, não cobra — ver [[feedback_orientar_nao_mandar]])

No máximo uma mensagem de cadência por semana (o gatilho é o domingo), e só
quando há algo NOVO a dizer. Substitui o gatilho por-corrida (uma-vez-e-pronto).
Espelha o PaceProgressNotifier. Ver item 26 de [[project_ideias_produto]]."""

from statistics import median

from app.application.history.workout_structure_builder import (
    WorkoutStructureBuilder,
)
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.persistence.cadence_progress_store import (
    CadenceProgressStore,
)
from app.infrastructure.persistence.dispatch_guard import DispatchGuard

# abaixo disto a cadência é claramente baixa (recreativo ~160-170; alvo ~170-180)
_LOW_SPM = 163

# na faixa econômica: chegou aqui, a missão da cadência está cumprida
_TARGET_SPM = 170

# ganho sustentado que já vale um "tá subindo" (acima do ruído natural)
_PROGRESS_GAIN = 3

# travou: só depois disto o coach dá o único re-cutução (e depois cala)
_STUCK_DAYS = 28

# amostras mínimas pra confiar na mediana (cadência varia com ritmo/terreno)
_MIN_SAMPLES = 3

# janela recente pra medir a cadência "de agora"
_WINDOW_DAYS = 42

# corrida de verdade (fragmento curto não representa a cadência)
_MIN_KM = 3.0

# mais lento que isto é trote/caminhada — cadência baixa é natural, não coacha
_WALK_PACE = 7.5  # min/km

# chave do gatilho ANTIGO (dica por-corrida): se já disparou, o loop engata
# silencioso (não re-manda a intro pra quem já recebeu)
_LEGACY_KIND = "form_cadence"


class CadenceProgressNotifier:

    @staticmethod
    def check(
        profile: str,
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> str | None:
        """Mensagem do loop de cadência (ou None se nada novo a dizer)."""

        current = CadenceProgressNotifier._current_cadence(history)

        if current is None:

            return None

        store = CadenceProgressStore()

        saved = store.load(profile)

        today = today_local()

        # --- loop ainda não engatou ---
        if saved is None:

            # cadência já ok: não há o que coachar
            if current >= _LOW_SPM:

                return None

            # já recebeu a dica inicial pelo gatilho antigo: engata o
            # acompanhamento SEM re-mandar a intro
            silent = DispatchGuard.already_sent(_LEGACY_KIND, profile, "v1")

            store.save(
                profile,
                state="watching",
                baseline_spm=current,
                anchor_date=today,
                re_nudged=False,
            )

            return (
                None
                if silent
                else CadenceProgressNotifier._initial(runner.name, current)
            )

        # --- alvo já batido antes: encerrado, silêncio pra sempre ---
        if saved.get("state") == "closed":

            return None

        # --- acompanhando ---
        baseline = int(saved.get("baseline_spm") or current)

        re_nudged = bool(saved.get("re_nudged"))

        # bateu o alvo → celebra e ENCERRA
        if current >= _TARGET_SPM:

            store.save(
                profile,
                state="closed",
                baseline_spm=current,
                anchor_date=today,
                re_nudged=re_nudged,
            )

            return CadenceProgressNotifier._celebration(runner.name, current)

        # subiu de forma sustentada (ainda < alvo) → reconhece e re-ancora
        if current - baseline >= _PROGRESS_GAIN:

            store.save(
                profile,
                state="watching",
                baseline_spm=current,
                anchor_date=today,
                re_nudged=False,
            )

            return CadenceProgressNotifier._progress(
                runner.name, baseline, current
            )

        # travou: UM re-cutução depois de ~4 semanas, e para
        anchor = CadenceProgressNotifier._parse_date(saved.get("anchor_date"))

        if (
            not re_nudged
            and anchor is not None
            and (today - anchor).days >= _STUCK_DAYS
        ):

            store.save(
                profile,
                state="watching",
                baseline_spm=baseline,
                anchor_date=today,
                re_nudged=True,
            )

            return CadenceProgressNotifier._stuck(runner.name, current)

        return None

    @staticmethod
    def _current_cadence(history: TrainingHistory) -> int | None:
        """Mediana de cadência (spm) das corridas RECENTES qualificadas —
        corrida de verdade (≥3 km), em ritmo de corrida (não trote), com
        cadência medida. None se não houver amostra suficiente pra confiar."""

        cutoff = today_local()

        values: list[int] = []

        for activity in history.activities:

            if not is_run_sport(activity.sport):

                continue

            if activity.distance / 1000 < _MIN_KM:

                continue

            # dentro da janela recente
            if (cutoff - activity.start_date.date()).days > _WINDOW_DAYS:

                continue

            # trote/caminhada: cadência baixa é esperada, não entra
            speed = activity.average_speed

            if not speed or (1000 / speed) / 60 > _WALK_PACE:

                continue

            cadence = WorkoutStructureBuilder._cadence(activity.raw or {})

            if cadence:

                values.append(cadence)

        if len(values) < _MIN_SAMPLES:

            return None

        return int(round(median(values)))

    @staticmethod
    def _parse_date(value):

        from datetime import date

        try:

            return date.fromisoformat(value) if value else None

        except (TypeError, ValueError):

            return None

    @staticmethod
    def _initial(name: str, cadence: int) -> str:

        return (
            f"👟 Uma dica de forma, {name}: sua cadência hoje foi ~{cadence} "
            "passos/min. Mirar 170-175 — passos um pouco mais curtos e "
            "rápidos, sem forçar o ritmo — reduz o impacto a cada passada, te "
            "deixa mais econômico e protege de lesão. É velocidade quase de "
            "graça. 🎯\n\nPra treinar: num trecho da próxima corrida, conte os "
            "passos de UM pé em 30s e multiplique por 4 — mire uns 85-88."
        )

    @staticmethod
    def _progress(name: str, before: int, now: int) -> str:

        return (
            f"📈 Tua cadência tá subindo, {name}: de ~{before} pra ~{now} "
            "passos/min. É exatamente o caminho — passos mais curtos e "
            "rápidos. Segue mirando 170-175, você tá quase lá. 👊"
        )

    @staticmethod
    def _celebration(name: str, cadence: int) -> str:

        return (
            f"🎯 Cadência no ponto, {name}! Você chegou a ~{cadence} "
            "passos/min, dentro da faixa econômica (170-175). Menos impacto, "
            "mais eficiência e corrida mais protegida de lesão — exatamente o "
            "que a gente buscava. Missão da cadência cumprida. 👏"
        )

    @staticmethod
    def _stuck(name: str, cadence: int) -> str:

        return (
            f"👟 Voltando na cadência, {name}: ainda tá em ~{cadence} "
            "passos/min. Um jeito que costuma destravar: por 20-30 segundos, "
            "4-5 vezes numa corrida leve, dê passadas curtinhas e MAIS rápidas "
            "(sem acelerar o pace, só girando as pernas mais vezes) — deixa o "
            "corpo achar o ritmo novo. Correr no compasso de uma música de "
            "~175 BPM também ajuda a fixar."
        )
