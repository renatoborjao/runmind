"""A ESTRATÉGIA DE PROVA — pace, planos A/B/C, passagens de controle, calor e nutrição.

Antes a estratégia pegava a META como verdade e fechava sempre com "O ritmo está dentro
do que você treinou — confia no plano", mesmo quando não estava: o Maurício quer 1:22:30
nos 15 km (5:30/km) e os números dele dizem entre ~1:24:27 (Garmin) e ~1:29:41 (seus
treinos). Agora o cartão é HONESTO com o que os números mostram e dá um plano pra cada
tipo de dia:

- A · ousado — a meta (ou o melhor que as fontes sustentam quando a meta é folgada);
- B · realista — o que os números do atleta sustentam hoje;
- C · seguro — pro dia difícil (calor, sono ruim, perna pesada).

Onde a meta cai na FAIXA dos números (histórico × Garmin, [[race_forecast]]) decide o
plano de largada: meta à frente de tudo = larga no B e só vai pro A se a passagem de
controle confirmar. Passagens nos terços da prova pra decidir NO DIA, e ajuste de calor
na semana da prova (previsão do tempo, [[race_heat]]). A nutrição segue o advisor dos
longões ([[fueling_advisor]]). Puro/determinístico — a previsão e o clima entram de
fora. Ver [[project_race_intel]]."""

from dataclasses import dataclass, field

from app.application.history.race_forecast import range_sentence
from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.race_time_formatter import RaceTimeFormatter
from app.application.races.race_heat import STRONG_HEAT_PCT
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_goal import TrainingGoal

# quanto abrir mais devagar / fechar mais forte que o pace médio (min/km).
# ~5 s/km pra cada lado: largada segura sem jogar tempo fora, final forte.
_SPLIT_OFFSET_MIN = 5 / 60

# a meta a menos disto (s) da ponta rápida da faixa conta como DENTRO dela (mesma folga
# da previsão em faixa)
_ON_TARGET_SLACK_S = 20

# separação mínima entre os planos (A < B < C), pra não virarem a mesma linha
_MIN_GAP_AB = 1.01
_MIN_GAP_BC = 1.015

# sem nenhuma evidência além da meta/estimativa: o B e o C são margens de dia
_NO_EVIDENCE_B = 1.015
_NO_EVIDENCE_C = 1.03


@dataclass(slots=True)
class RacePacePlan:

    distance_km: float
    estimated: bool          # True = tempo veio da forma atual, não de um alvo
    total_minutes: float     # tempo-alvo (ou estimado) em minutos
    avg_pace_min: float      # pace médio (min/km)
    open_pace_min: float     # 1ª metade, controlado
    close_pace_min: float    # 2ª metade, mais forte
    halfway_minutes: float   # passagem na metade da distância


@dataclass(slots=True)
class RaceScenario:

    letter: str              # "A" | "B" | "C"
    role: str                # ousado | realista | seguro
    total_minutes: float
    avg_pace_min: float
    is_target: bool = False  # é exatamente a meta que o atleta definiu


@dataclass(slots=True)
class RaceScenarios:

    distance_km: float
    items: list[RaceScenario] = field(default_factory=list)
    # onde a meta cai nos números do atleta: beyond (à frente de tudo) | inside (cabe na
    # faixa) | beaten (mais lenta que tudo). None = sem meta ou sem evidência.
    position: str | None = None
    checkpoints: list[int] = field(default_factory=list)


class RaceStrategyEngine:

    @staticmethod
    def build(
        runner_name: str,
        goal: TrainingGoal,
        metrics: RunnerMetrics | None = None,
        profile: str | None = None,
        pred: dict | None = None,
        heat: dict | None = None,
    ) -> str | None:
        """Mensagem da estratégia, ou None se não dá pra montar (sem distância
        e sem tempo-alvo nem forma pra estimar). `profile` (slug) deixa a nutrição
        do dia da prova respeitar as restrições da aba Nutrição. `pred`: a previsão
        do atleta (histórico × Garmin, `RaceTimePredictor.predict_formatted`) — sem
        ela o cartão não afirma nada sobre os números dele. `heat`: o calor previsto
        pro dia (`RaceHeat.for_race`), só na semana da prova."""

        plan = RaceStrategyEngine.plan(goal, metrics)

        if plan is None:

            return None

        scenarios = RaceStrategyEngine.scenarios(plan, pred)

        return RaceStrategyEngine._message(
            runner_name, goal, plan, profile, scenarios, pred, heat,
        )

    @staticmethod
    def plan(
        goal: TrainingGoal,
        metrics: RunnerMetrics | None = None,
    ) -> RacePacePlan | None:

        distance = goal.distance_km or 0.0

        if distance <= 0:

            return None

        total_minutes = RaceStrategyEngine._target_minutes(goal, distance, metrics)

        if total_minutes is None:

            return None

        avg = total_minutes / distance

        open_pace = avg + _SPLIT_OFFSET_MIN
        close_pace = avg - _SPLIT_OFFSET_MIN

        # passagem na metade correndo a 1ª metade no pace controlado
        halfway = open_pace * (distance / 2)

        return RacePacePlan(
            distance_km=distance,
            estimated=goal.target_time is None,
            total_minutes=total_minutes,
            avg_pace_min=avg,
            open_pace_min=open_pace,
            close_pace_min=close_pace,
            halfway_minutes=halfway,
        )

    # ------------------------------------------------------------------
    # os três planos

    @staticmethod
    def scenarios(plan: RacePacePlan, pred: dict | None = None) -> RaceScenarios:
        """Os planos A (ousado) · B (realista) · C (seguro), do mais rápido ao mais
        lento, e onde a META cai nos números do atleta (`pred`, com a faixa histórico
        × Garmin quando as fontes discordam)."""

        distance = plan.distance_km

        target = None if plan.estimated else plan.total_minutes * 60

        evidence = RaceStrategyEngine._evidence(pred)

        position = None

        if target is None:

            if evidence:

                low, high = evidence

                a = low

                b = (low + high) / 2 if high > low * _MIN_GAP_AB else low * _NO_EVIDENCE_B

                c = max(high, b * 1.02)

            else:

                estimate = plan.total_minutes * 60

                a, b, c = estimate * 0.985, estimate, estimate * _NO_EVIDENCE_C

        elif evidence is None:

            a, b, c = target, target * _NO_EVIDENCE_B, target * _NO_EVIDENCE_C

        else:

            low, high = evidence

            if target < low - _ON_TARGET_SLACK_S:

                position = "beyond"

                a, b, c = target, low, max(high, low * 1.03)

            elif target <= high:

                position = "inside"

                a = target

                b = max((target + high) / 2, target * _MIN_GAP_AB)

                c = max(high * 1.02, b * 1.02)

            else:

                position = "beaten"

                a, b, c = low, target, target * 1.03

        b = max(b, a * _MIN_GAP_AB)

        c = max(c, b * _MIN_GAP_BC)

        items = [
            RaceScenario("A", "ousado", a / 60, a / 60 / distance),
            RaceScenario("B", "realista", b / 60, b / 60 / distance),
            RaceScenario("C", "seguro", c / 60, c / 60 / distance),
        ]

        # o plano que É a meta (a menos de 1 s do tempo declarado)
        if target is not None:

            for item in items:

                if abs(item.total_minutes * 60 - target) < 1:

                    item.is_target = True

        return RaceScenarios(
            distance_km=distance,
            items=items,
            position=position,
            checkpoints=RaceStrategyEngine._checkpoints(distance),
        )

    @staticmethod
    def _evidence(pred: dict | None) -> tuple[float, float] | None:
        """(mais rápido, mais lento) dos números do atleta, em segundos: a faixa
        histórico × Garmin quando as fontes discordam, senão o número do histórico."""

        if not pred:

            return None

        forecast = pred.get("range")

        if forecast:

            return float(forecast["low_seconds"]), float(forecast["high_seconds"])

        seconds = pred.get("seconds")

        return (float(seconds), float(seconds)) if seconds else None

    @staticmethod
    def _checkpoints(distance_km: float) -> list[int]:
        """Onde conferir o tempo: nos terços (15 km: 5 e 10; meia: 7 e 14); prova de
        8–12 km, só na metade; curta demais, nenhuma."""

        if distance_km >= 12:

            return [round(distance_km / 3), round(distance_km * 2 / 3)]

        if distance_km >= 8:

            return [round(distance_km / 2)]

        return []

    @staticmethod
    def _passage_minutes(total_minutes: float, distance_km: float, km: int) -> float:
        """Tempo na passagem do km `km` correndo a 1ª metade ~5 s/km mais lenta e a
        2ª ~5 s/km mais forte que o pace médio do plano."""

        avg = total_minutes / distance_km

        open_pace = avg + _SPLIT_OFFSET_MIN

        close_pace = avg - _SPLIT_OFFSET_MIN

        half = distance_km / 2

        if km <= half:

            return km * open_pace

        return half * open_pace + (km - half) * close_pace

    @staticmethod
    def _target_minutes(
        goal: TrainingGoal,
        distance: float,
        metrics: RunnerMetrics | None,
    ) -> float | None:
        """Minutos-alvo: do tempo declarado, senão estimado pela forma atual
        (pace de limiar ≈ ritmo de prova de ~10k). Sem nenhum dos dois, None."""

        parsed = RaceStrategyEngine._parse_time(goal.target_time)

        if parsed is not None:

            return parsed

        if metrics is not None and metrics.threshold_pace > 0:

            return metrics.threshold_pace * distance

        return None

    @staticmethod
    def _parse_time(target_time: str | None) -> float | None:
        """"00:50:00"/"50:00" -> minutos (float). Formato inválido -> None."""

        if not target_time:

            return None

        parts = target_time.split(":")

        try:

            nums = [int(p) for p in parts]

        except ValueError:

            return None

        if len(nums) == 3:

            h, m, s = nums

        elif len(nums) == 2:

            h, m, s = 0, nums[0], nums[1]

        else:

            return None

        total = h * 60 + m + s / 60

        return total if total > 0 else None

    @staticmethod
    def _fueling(plan: RacePacePlan, profile: str | None) -> list[str]:
        """As linhas de nutrição do dia da prova (as do advisor dos longões).
        Best-effort: falhou = a estratégia sai sem a linha, nunca quebra."""

        try:

            from app.application.planner.fueling_advisor import race_fueling_lines

            return race_fueling_lines(plan.total_minutes, profile)

        except Exception as e:  # noqa: BLE001

            print(f"Estratégia de prova: nutrição falhou p/ '{profile}': {e}")

            return []

    # ------------------------------------------------------------------
    # a mensagem

    @staticmethod
    def _numbers_sentence(
        scenarios: RaceScenarios, goal: TrainingGoal, pred: dict | None,
    ) -> str:
        """O que os números do atleta dizem da META — honesto. Vazio sem meta ou sem
        previsão (não afirmamos nada que não sabemos)."""

        if scenarios.position is None or not pred:

            return ""

        target = RaceTimeFormatter.format(
            (RaceStrategyEngine._parse_time(goal.target_time) or 0) * 60
        )

        forecast = pred.get("range")

        phrase = (
            range_sentence(forecast)
            if forecast
            else f"~{RaceTimeFormatter.format(pred['seconds'])} (seus treinos)"
        )

        first = scenarios.checkpoints[0] if scenarios.checkpoints else None

        if scenarios.position == "beyond":

            where = f"do km {first}" if first else "da metade"

            return (
                f"⚠️ Sua meta ({target}) está à frente do que seus números mostram "
                f"hoje: {phrase}. Por isso: largue no plano B e só vá pro A se a "
                f"passagem {where} confirmar — largar na meta sem a base é o jeito "
                "mais comum de quebrar nos últimos km."
            )

        if scenarios.position == "inside":

            return (
                f"Sua meta ({target}) cabe na faixa dos seus números: {phrase}. É o "
                "plano A — possível, mas pede um dia bom. O B é a sua rede de segurança."
            )

        return (
            f"Seus números mostram que dá pra ir mais rápido que a sua meta "
            f"({target}): {phrase}. O A é um desafio possível; o B é a meta que você "
            "definiu."
        )

    @staticmethod
    def _plans_lines(scenarios: RaceScenarios) -> list[str]:

        lines = ["Três planos pro dia:"]

        for s in scenarios.items:

            tag = " ← sua meta" if s.is_target else ""

            lines.append(
                f"• {s.letter} · {s.role} — "
                f"{RaceStrategyEngine._fmt_duration(s.total_minutes)} · "
                f"{PaceFormatter.format(s.avg_pace_min)}/km{tag}"
            )

        return lines

    @staticmethod
    def _heat_lines(scenarios: RaceScenarios, heat: dict | None) -> list[str]:
        """O calor previsto pro dia e os paces já ajustados. Vazio sem previsão."""

        if not heat:

            return []

        temp = round(heat["temp"])

        feels = round(heat["feels"])

        pct = float(heat.get("penalty_pct") or 0)

        place = f"{heat['where']}, " if heat.get("where") else ""

        head = f"🌡️ Previsão pro dia ({place}largada às {heat['hour']}h): ~{temp}°C"

        if pct <= 0:

            return [f"{head} — sem ajuste de ritmo pelo clima."]

        paces = " · ".join(
            f"{s.letter} {PaceFormatter.format(s.avg_pace_min * (1 + pct / 100))}"
            for s in scenarios.items
        )

        line = (
            f"{head}, sensação {feels}°C. O calor costuma custar ~{pct:g}% do ritmo — "
            f"no dia, use {paces} /km e hidrate mais cedo."
        )

        if pct >= STRONG_HEAT_PCT:

            line += " Calor forte: priorize terminar bem — se passar mal, vá pro C."

        return [line]

    @staticmethod
    def _checkpoint_lines(plan: RacePacePlan, scenarios: RaceScenarios) -> list[str]:

        if not scenarios.checkpoints:

            half_km = RaceStrategyEngine._fmt_distance(plan.distance_km / 2)

            halfway = RaceStrategyEngine._fmt_duration(plan.halfway_minutes)

            return [
                f"• Passagem nos {half_km} km: ~{halfway} (se chegar muito antes "
                "disso, segura; muito depois, é hora de acelerar)."
            ]

        lines = ["", "Passagens de controle (com a largada controlada):"]

        for km in scenarios.checkpoints:

            times = " · ".join(
                f"{s.letter} "
                + RaceStrategyEngine._fmt_duration(
                    RaceStrategyEngine._passage_minutes(
                        s.total_minutes, scenarios.distance_km, km,
                    )
                )
                for s in scenarios.items
            )

            lines.append(f"• km {km}: {times}")

        lines.append(
            "Na passagem: mais rápido que o A → segura (largar rápido cobra no fim); "
            "entre o A e o B → mantém; entre o B e o C → vai pro B sem tentar "
            "recuperar; atrás do C → pro C e termine bem. Terminar forte vale mais "
            "que o relógio."
        )

        return lines

    @staticmethod
    def _message(
        runner_name: str,
        goal: TrainingGoal,
        plan: RacePacePlan,
        profile: str | None = None,
        scenarios: RaceScenarios | None = None,
        pred: dict | None = None,
        heat: dict | None = None,
    ) -> str:

        scenarios = scenarios or RaceStrategyEngine.scenarios(plan, pred)

        distance = RaceStrategyEngine._fmt_distance(plan.distance_km)
        avg = PaceFormatter.format(plan.avg_pace_min)

        if plan.estimated:

            abertura = (
                f"Pelo seu ritmo atual, {runner_name}, algo perto de "
                f"*{RaceStrategyEngine._fmt_duration(plan.total_minutes)}* nos "
                f"{distance} km é realista. Se tiver um tempo-alvo, me fala que "
                "eu recalibro. Mas já vai a estratégia:"
            )

        else:

            abertura = (
                f"🏁 Estratégia pra sua prova, {runner_name} "
                f"({distance} km em "
                f"{RaceStrategyEngine._fmt_duration(plan.total_minutes)}):"
            )

        linhas = [abertura]

        numbers = RaceStrategyEngine._numbers_sentence(scenarios, goal, pred)

        if numbers:

            linhas += ["", numbers]

        linhas += [
            "",
            f"🎯 Pace-alvo médio: *{avg}/km*",
            "",
            *RaceStrategyEngine._plans_lines(scenarios),
        ]

        heat_lines = RaceStrategyEngine._heat_lines(scenarios, heat)

        if heat_lines:

            linhas += ["", *heat_lines]

        linhas += [
            "",
            "Como correr:",
            "• Largada CONTROLADA — primeira metade uns ~5 s/km mais lenta que o "
            "pace do plano escolhido. Todo mundo sai rápido demais; segurar aqui é "
            "o que salva o final.",
            "• Segunda metade uns ~5 s/km mais forte — é onde você passa os outros "
            "em vez de ser passado.",
            *RaceStrategyEngine._checkpoint_lines(plan, scenarios),
        ]

        # nutrição: a MESMA do plano dos longões (duração da prova, não distância)
        fueling = RaceStrategyEngine._fueling(plan, profile)

        if fueling:

            linhas += ["", *fueling]

        linhas += ["", RaceStrategyEngine._closing(scenarios)]

        return "\n".join(linhas)

    @staticmethod
    def _closing(scenarios: RaceScenarios) -> str:
        """O fecho — sem a promessa velha de que "o ritmo está dentro do que você
        treinou": só diz o que é verdade pra cada situação."""

        if scenarios.position == "beyond":

            return (
                "Largue no B, confie no que você treinou e deixe o corpo — não o "
                "relógio — decidir se o A é possível. 🚀"
            )

        return (
            "Escolha o plano pelo corpo na passagem, não pelo relógio. Confia no que "
            "você treinou. 🚀"
        )

    @staticmethod
    def reminder(
        goal: TrainingGoal,
        metrics: RunnerMetrics | None = None,
        pred: dict | None = None,
        heat: dict | None = None,
    ) -> str | None:
        """A linha curta dos toques de prova (semana/véspera/manhã): o pace e a
        largada controlada — e, quando a meta está à frente dos números do atleta, o
        plano B; com a previsão do dia, o ajuste de calor. None sem como estimar."""

        plan = RaceStrategyEngine.plan(goal, metrics)

        if plan is None:

            return None

        scenarios = RaceStrategyEngine.scenarios(plan, pred)

        a, b, c = (PaceFormatter.format(s.avg_pace_min) for s in scenarios.items)

        if scenarios.position == "beyond":

            first = scenarios.checkpoints[0] if scenarios.checkpoints else None

            where = f" Decida na passagem do km {first}." if first else ""

            line = (
                "🎯 Lembrete: largada CONTROLADA — plano B ~"
                f"{b}/km (A {a} só se confirmar, C {c}).{where}"
            )

        else:

            line = (
                f"🎯 Lembrete: pace-alvo ~{PaceFormatter.format(plan.avg_pace_min)}/km, "
                "largada controlada."
            )

        pct = float((heat or {}).get("penalty_pct") or 0)

        if heat and pct > 0:

            seconds = round(plan.avg_pace_min * pct / 100 * 60)

            line += (
                f" 🌡️ Calor previsto (~{round(heat['temp'])}°C): "
                f"o ritmo costuma pedir ~+{seconds} s/km."
            )

        return line

    @staticmethod
    def _fmt_distance(km: float) -> str:

        return f"{km:.0f}" if abs(km - round(km)) < 0.05 else f"{km:.1f}"

    @staticmethod
    def _fmt_duration(minutes: float) -> str:
        """Minutos (float) -> 'H:MM:SS' (>=1h) ou 'MM:SS'."""

        total_sec = round(minutes * 60)
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)

        if h > 0:

            return f"{h}:{m:02d}:{s:02d}"

        return f"{m}:{s:02d}"
