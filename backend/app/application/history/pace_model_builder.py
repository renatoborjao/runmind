"""Constrói o PaceModel do atleta — a FONTE ÚNICA de ritmos, ancorada em dados
REAIS e na condição dele:

1. VDOT do MELHOR esforço real (corrida que ele de fato completou) -> ritmos
   E/M/T/I/R por fisiologia. Como parte do que ele fez, é sustentável.
2. TRAVA DE CONDIÇÃO: o fácil nunca sai mais rápido do que o ritmo leve que ele
   REALMENTE corre. A regra do Renato — não mandar "pace 4" pra quem sustenta
   5:45; o modelo se recusa a matar o atleta.
3. Sem esforço real (estreante): cai num modelo conservador do pace declarado.

Puro/determinístico. Garmin premium (limiar medido) entra por cima quando houver
(follow-up). Ver [[VdotCalculator]] e [[project_pace_so_corrida]]."""

from statistics import median

from app.application.history.vdot_calculator import (
    FRAC_EASY_FAST,
    FRAC_EASY_SLOW,
    FRAC_INTERVAL,
    FRAC_MARATHON,
    FRAC_REP,
    FRAC_THRESHOLD,
    VdotCalculator,
)
from app.domain.entities.pace_model import (
    SOURCE_DECLARED,
    SOURCE_ROOKIE,
    SOURCE_VDOT,
    PaceModel,
)
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import is_run_sport

# corrida curta demais não é âncora confiável de VDOT (ruído/GPS)
_ANCHOR_MIN_KM = 2.0

# faixa de pace plausível pra um esforço humano de ≥2 km (corta erro de GPS)
_MIN_PACE = 2.5   # min/km (mais rápido que isso em 2 km+ é erro)
_MAX_PACE = 9.0   # min/km (acima é caminhada, não corrida)

# a ponta rápida do fácil não pode passar disto além do ritmo leve REAL do
# atleta (6 s/km) — margem mínima pra empurrar sem virar sofrimento
_EASY_GUARD_MARGIN = 0.10

# largura mínima da faixa fácil, pra nunca sair um fácil "de um pace só"
_MIN_EASY_SPREAD = 0.30

# default conservador de estreante (nunca correu / não informou)
_ROOKIE_PACE = 8.0


class PaceModelBuilder:

    @staticmethod
    def build(
        history: TrainingHistory,
        runner: RunnerProfile | None = None,
    ) -> PaceModel:

        paces = PaceModelBuilder._real_run_paces(history)

        if not paces:

            return PaceModelBuilder._fallback(runner)

        vdot = PaceModelBuilder._best_vdot(history)

        # ÂNCORA CONTÍNUA: o VDOT do melhor esforço SUSTENTADO (best_efforts do
        # Strava, atualizados no domingo) é mais fiel que a média da corrida —
        # captura o tempo/tiro que a média dilui. Quando existe e é maior, ele
        # ancora (nunca rebaixa). Ver [[project_modelo_pace_vdot]].
        vdot = PaceModelBuilder._higher(
            vdot, PaceModelBuilder._best_effort_floor(runner)
        )

        if vdot is None:

            return PaceModelBuilder._fallback(runner)

        return PaceModelBuilder._from_vdot(vdot, paces)

    # ------------------------------------------------------------------

    @staticmethod
    def _best_effort_floor(runner: RunnerProfile | None) -> float | None:
        """Marca-d'água do VDOT contínuo do atleta (best_efforts do Strava).
        Best-effort: sem store/sem dado → None e o modelo segue pela média."""

        profile = getattr(runner, "id", None) if runner else None

        if not profile:

            return None

        try:

            from app.infrastructure.persistence.best_effort_vdot_store import (
                BestEffortVdotStore,
            )

            return BestEffortVdotStore().max_vdot(profile)

        except Exception:

            return None

    @staticmethod
    def _higher(a: float | None, b: float | None) -> float | None:

        values = [v for v in (a, b) if v is not None]

        return max(values) if values else None

    @staticmethod
    def _real_run_paces(history: TrainingHistory) -> list[float]:
        """Paces (min/km) das corridas REAIS utilizáveis (≥ âncora, sem
        caminhada nem erro de GPS)."""

        paces = []

        for a in history.activities:

            if not is_run_sport(a.sport) or a.average_speed <= 0:

                continue

            if a.distance / 1000 < _ANCHOR_MIN_KM:

                continue

            pace = (1000 / a.average_speed) / 60

            if _MIN_PACE <= pace <= _MAX_PACE:

                paces.append(pace)

        return paces

    @staticmethod
    def _best_vdot(history: TrainingHistory) -> float | None:
        """O MAIOR VDOT entre as corridas reais — o melhor esforço que o atleta
        já demonstrou. É a âncora de capacidade (grounded no que ele fez)."""

        best = None

        for a in history.activities:

            if not is_run_sport(a.sport) or a.average_speed <= 0:

                continue

            if a.distance / 1000 < _ANCHOR_MIN_KM:

                continue

            pace = (1000 / a.average_speed) / 60

            if not (_MIN_PACE <= pace <= _MAX_PACE):

                continue

            # tempo do esforço a partir do pace real (consistente com o filtro
            # acima), não do moving_time — robusto a quirks de dado
            seconds = a.distance / a.average_speed

            vdot = VdotCalculator.vdot(a.distance, seconds)

            if best is None or vdot > best:

                best = vdot

        return best

    @staticmethod
    def _from_vdot(vdot: float, paces: list[float]) -> PaceModel:
        """Ritmos E/M/T/I/R do VDOT + a trava de condição no fácil."""

        easy_fast = VdotCalculator.pace_min_km(vdot, FRAC_EASY_FAST)

        easy_slow = VdotCalculator.pace_min_km(vdot, FRAC_EASY_SLOW)

        # ritmo leve REAL do atleta = mediana das corridas mais lentas que a
        # mediana geral (os dias tranquilos dele)
        overall = median(paces)

        easy_days = [p for p in paces if p >= overall]

        observed_easy = median(easy_days) if easy_days else overall

        # TRAVA: o fácil não pode ser mais rápido que o leve real dele (+margem)
        floor = observed_easy - _EASY_GUARD_MARGIN

        capped = easy_fast < floor

        easy_min = floor if capped else easy_fast

        easy_max = max(easy_slow, easy_min + _MIN_EASY_SPREAD)

        return PaceModel(
            easy_min=round(easy_min, 2),
            easy_max=round(easy_max, 2),
            marathon=round(VdotCalculator.pace_min_km(vdot, FRAC_MARATHON), 2),
            threshold=round(VdotCalculator.pace_min_km(vdot, FRAC_THRESHOLD), 2),
            interval=round(VdotCalculator.pace_min_km(vdot, FRAC_INTERVAL), 2),
            rep=round(VdotCalculator.pace_min_km(vdot, FRAC_REP), 2),
            vdot=round(vdot, 1),
            source=SOURCE_VDOT,
            easy_capped=capped,
        )

    @staticmethod
    def _fallback(runner: RunnerProfile | None) -> PaceModel:
        """Sem corrida real: modelo CONSERVADOR do pace declarado (ou default de
        estreante). Enviesado pro lento — nunca puxa demais quem mal correu."""

        declared = getattr(runner, "initial_pace_min_km", None) if runner else None

        pace = declared or _ROOKIE_PACE

        source = SOURCE_DECLARED if declared else SOURCE_ROOKIE

        return PaceModel(
            easy_min=round(pace, 2),
            easy_max=round(pace + 0.55, 2),
            marathon=round(pace - 0.25, 2),
            threshold=round(pace - 0.45, 2),
            interval=round(pace - 0.90, 2),
            rep=round(pace - 1.15, 2),
            vdot=None,
            source=source,
            easy_capped=False,
        )
