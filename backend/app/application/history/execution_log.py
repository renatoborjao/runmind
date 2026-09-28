"""PLANEJADO × EXECUTADO, vivo: sessão a sessão, o alvo que o coach prescreveu ×
o que o atleta fez de verdade (blocos do relógio quando há, FC, o que ele
sentiu). É a base de onde a IA CALIBRA os alvos e lê a EVOLUÇÃO — aqui só
FATOS, a leitura é dela. Substitui a auto-calibração antiga, que guardava um
viés mediano e mandava "aperte"/"afrouxe": mediu com a régua errada e precisou
ser zerada à mão (27/09). Renato 28/09: "o coach precisa, com a base dos
treinos, ver o planejado × executado, saber o que propor e ter a visão se o
atleta está evoluindo".

Os blocos (voltas rotuladas do Garmin × passos prescritos) só existem na hora
da análise — o arquivo reduzido não guarda voltas — por isso o pós-treino grava
o resumo ([[execution_log_store]]) e o dossiê lê de volta."""

from datetime import date
from statistics import mean

from app.application.history.stimulus_ledger import (
    EASY,
    LONG,
    RACE,
    RACE_PACE,
    STEADY,
    THRESHOLD,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.workout_step import INTERVAL, RUN

WINDOW_WEEKS = 6

# blocos que carregam o estímulo — aquecimento/desaquecimento/pausas ficam fora
_STIMULUS_KINDS = {RUN, INTERVAL}

# estímulos CONTÍNUOS — só neles a média da corrida mede o alvo (no fartlek/
# VO2/subida a média fica entre o forte e o trote e não diz nada)
_CONTINUOUS = {EASY, STEADY, LONG, THRESHOLD, RACE, RACE_PACE}

# a partir de quantos blocos iguais seguidos vira resumo ("tiros 8× 200 m")
_GROUP_MIN = 3

_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")

HEADER = (
    "PLANEJADO × EXECUTADO (sessão a sessão, últimas {weeks} semanas: o alvo "
    "que VOCÊ prescreveu → o que ele fez de verdade, com FC e o que ele "
    "sentiu; blocos = voltas do relógio pareadas com os passos). É daqui que "
    "sai a CALIBRAÇÃO, viva, a cada decisão: tiros/blocos repetidamente mais "
    "lentos que a faixa com esforço alto = o alvo passou do que ele sustenta "
    "hoje (afrouxe); cravando a faixa com FC controlada e esforço moderado, "
    "semana após semana = ele comporta o próximo degrau (suba um passo); "
    "sobrando com folga = alvo frouxo. No leve/longão-base a faixa é TETO — "
    "sair mais rápido ali é falta de controle, não sinal pra subir alvo. E a "
    "EVOLUÇÃO: compare sessões do mesmo estímulo ao longo das semanas (ritmo, "
    "FC e esforço) — mais rápido na mesma FC/esforço = evoluindo; igual ou "
    "pior com o esforço subindo = estagnou ou está cansado. Um dia isolado "
    "(calor, noite ruim) não é padrão."
)


def entry_from_comparison(comparison) -> dict | None:
    """Resumo persistível da comparação bloco-a-bloco: só os blocos de
    estímulo (contínuo e tiro) + o que ficou por fazer. None sem comparação."""

    if comparison is None:

        return None

    blocks = []

    for block in comparison.blocks:

        if block.kind not in _STIMULUS_KINDS:

            continue

        blocks.append({
            "kind": block.kind,
            "m": round(block.executed_distance_m or 0),
            "pace": (
                PaceFormatter.format(block.executed_pace)
                if block.executed_pace else None
            ),
            "hr": block.executed_hr,
            "target": (
                f"{block.pace_min}-{block.pace_max}"
                if block.pace_min and block.pace_max else None
            ),
            "ok": block.within_target,
        })

    if not blocks and not comparison.missing:

        return None

    return {"blocks": blocks, "missing": list(comparison.missing)}


class ExecutionLog:

    @staticmethod
    def render(
        plans, activities, log: dict[int, dict], rpes, today: date,
        weeks: int = WINDOW_WEEKS,
    ) -> str:

        from app.application.history.training_patterns import TrainingPatterns

        sessions = TrainingPatterns._sessions(plans, activities, today, weeks)

        by_day = {str(getattr(r, "day", "")): r for r in rpes or []}

        lines = []

        for day, session, family, act in sessions:

            if act is None and day >= today:

                continue  # a de hoje ainda pode sair

            lines.append(
                ExecutionLog._line(
                    day, session, family, act, log, by_day.get(day.isoformat()),
                )
            )

        if not lines:

            return ""

        return HEADER.format(weeks=weeks) + "\n" + "\n".join(lines)

    @staticmethod
    def for_profile(profile: str) -> str:
        """Render a partir do storage. Best-effort: falha vira ""."""

        try:

            from app.core.clock import today_local
            from app.domain.value_objects.sports import is_foot_sport
            from app.infrastructure.persistence.activity_archive_repository import (
                ActivityArchiveRepository,
            )
            from app.infrastructure.persistence.execution_log_store import (
                ExecutionLogStore,
            )
            from app.infrastructure.persistence.session_rpe_repository import (
                SessionRpeRepository,
            )
            from app.infrastructure.persistence.weekly_plan_repository import (
                WeeklyPlanRepository,
            )

            repo = WeeklyPlanRepository()

            plans = list(repo.history(profile))

            current = repo.load(profile)

            if current is not None:

                plans.append(current)

            activities = [
                a for a in ActivityArchiveRepository().load_activities(profile)
                if is_foot_sport(a.sport)
            ]

            return ExecutionLog.render(
                plans,
                activities,
                ExecutionLogStore().all(profile),
                SessionRpeRepository().load_sessions(profile),
                today_local(),
            )

        except Exception as e:

            print(f"Planejado × executado falhou p/ '{profile}': {e}")

            return ""

    # ------------------------------------------------------------------

    @staticmethod
    def _line(day: date, session, family: str, act, log: dict, rpe) -> str:

        planned = session.workout_type

        bits = []

        if session.planned_distance_km:

            bits.append(f"{session.planned_distance_km:g} km")

        elif session.planned_duration_minutes:

            bits.append(f"{session.planned_duration_minutes:g} min")

        target, comparable = ExecutionLog._session_target(session, family)

        if target:

            bits.append(f"alvo {target}")

        if bits:

            planned += f" ({'; '.join(bits)})"

        head = f"- {_WEEKDAYS[day.weekday()]} {day:%d/%m} · {planned} → "

        if act is None:

            return head + "NÃO FEZ"

        done = f"{(act.distance or 0) / 1000:.1f} km"

        if session.planned_duration_minutes and act.moving_time:

            done += f" em {act.moving_time / 60:.0f} min"

        pace = PaceFormatter.for_activity(
            act.distance, act.moving_time, getattr(act, "average_speed", None),
        )

        if pace:

            done += f" a {pace}"

        if getattr(act, "average_heartrate", None):

            done += f", FC {act.average_heartrate:.0f}"

        entry = ExecutionLog._entry_for(act, log)

        blocks = ExecutionLog._blocks_text(entry) if entry else ""

        if blocks:

            done += f" · blocos: {blocks}"

        elif ExecutionLog._has_intervals(session.steps):

            aims = sorted(ExecutionLog._targets(session.steps, kinds={INTERVAL}))

            aim = f" (alvo {', '.join(aims)})" if aims else ""

            done += f" · tiros{aim} sem voltas medidas (a média não mede tiro)"

        elif comparable and pace:

            done += f" ({ExecutionLog._vs(pace, comparable)})"

        if rpe is not None and getattr(rpe, "rpe", None) is not None:

            feel = f" ({rpe.feel})" if getattr(rpe, "feel", None) else ""

            done += f" · sentiu {rpe.rpe}/10{feel}"

        return head + done

    @staticmethod
    def _session_target(session, family: str) -> tuple[str | None, str | None]:
        """(alvo pra mostrar, alvo pra comparar com a MÉDIA). Sessão com
        tiros ou vários ritmos: o alvo da sessão é só um envelope (5:05-6:40
        num longão misto) — nenhum dos dois; os blocos carregam os alvos. Um
        ritmo só nos passos: é ele. Sem passos (planos antigos): mostra o da
        sessão, mas só compara a média no leve (contínuo por natureza)."""

        if ExecutionLog._has_intervals(session.steps):

            return None, None

        targets = ExecutionLog._targets(session.steps)

        if len(targets) > 1:

            return None, None

        if targets:

            only = targets.pop()

            return only, (only if family in _CONTINUOUS else None)

        target = ExecutionLog._range(session.target_pace_min, session.target_pace_max)

        return target, (target if family == EASY else None)

    @staticmethod
    def _targets(steps, kinds=_STIMULUS_KINDS) -> set[str]:

        out: set[str] = set()

        for step in steps or []:

            if getattr(step, "kind", None) in kinds and step.pace_min and step.pace_max:

                out.add(f"{step.pace_min}-{step.pace_max}")

            out |= ExecutionLog._targets(getattr(step, "steps", None), kinds)

        return out

    @staticmethod
    def _entry_for(act, log: dict) -> dict | None:
        """A execução gravada desta corrida: pelo id; senão pelo dia + a
        distância mais próxima (a mesma corrida vem com ids diferentes do
        Garmin e do Strava)."""

        if act.id in log:

            return log[act.id]

        from app.application.history.training_patterns import TrainingPatterns

        day = TrainingPatterns._local_day(act.start_date).isoformat()

        km = (act.distance or 0) / 1000

        same_day = [e for e in log.values() if e.get("date") == day]

        if not same_day:

            return None

        best = min(same_day, key=lambda e: abs((e.get("km") or 0) - km))

        return best if abs((best.get("km") or 0) - km) <= max(1.0, km * 0.15) else None

    @staticmethod
    def _blocks_text(entry: dict) -> str:

        groups: list[tuple[tuple, list[dict]]] = []

        for block in entry.get("blocks") or []:

            key = (block.get("kind"), block.get("target"))

            if groups and groups[-1][0] == key:

                groups[-1][1].append(block)

            else:

                groups.append((key, [block]))

        parts = []

        for (kind, target), items in groups:

            if len(items) >= _GROUP_MIN:

                parts.append(ExecutionLog._group_text(kind, target, items))

            else:

                parts += [ExecutionLog._block_text(b) for b in items]

        if entry.get("missing"):

            parts.append("não fez: " + ", ".join(entry["missing"]))

        return " | ".join(parts)

    @staticmethod
    def _group_text(kind: str, target: str | None, items: list[dict]) -> str:

        name = "tiros" if kind == INTERVAL else "trechos"

        sizes = {round((b.get("m") or 0) / 50) * 50 for b in items}

        size = (
            f"{len(items)}× {ExecutionLog._dist(sizes.pop())}"
            if len(sizes) == 1 else f"{len(items)}"
        )

        text = f"{name} {size}"

        if target:

            text += f" (alvo {target})"

        facts = []

        checked = [b for b in items if b.get("ok") is not None]

        if checked:

            on = sum(1 for b in checked if b["ok"])

            facts.append(f"{on} de {len(items)} no alvo")

        paces = sorted(
            (s, b["pace"]) for b in items
            if b.get("pace") and (s := ExecutionLog._sec(b["pace"])) is not None
        )

        if paces:

            facts.append(
                paces[0][1] if paces[0][1] == paces[-1][1]
                else f"{paces[0][1]} a {paces[-1][1]}"
            )

        hrs = [b["hr"] for b in items if b.get("hr")]

        if hrs:

            facts.append(f"FC ~{mean(hrs):.0f}")

        return text + (": " + ", ".join(facts) if facts else "")

    @staticmethod
    def _block_text(block: dict) -> str:

        name = "tiro" if block.get("kind") == INTERVAL else "contínuo"

        text = f"{name} {ExecutionLog._dist(block.get('m') or 0)}"

        if block.get("pace"):

            text += f" a {block['pace']}"

        if block.get("target") and block.get("pace"):

            text += f" (alvo {block['target']}: {ExecutionLog._vs(block['pace'], block['target'])})"

        if block.get("hr"):

            text += f", FC {block['hr']}"

        return text

    @staticmethod
    def _vs(pace: str, target: str) -> str:
        """Executado contra a FAIXA: dentro = na faixa; fora = quantos s/km."""

        fast, _, slow = target.partition("-")

        executed, fast_s, slow_s = (
            ExecutionLog._sec(pace), ExecutionLog._sec(fast), ExecutionLog._sec(slow),
        )

        if None in (executed, fast_s, slow_s):

            return "?"

        fast_s, slow_s = min(fast_s, slow_s), max(fast_s, slow_s)

        if executed > slow_s:

            return f"{executed - slow_s}s/km mais lento"

        if executed < fast_s:

            return f"{fast_s - executed}s/km mais rápido"

        return "na faixa"

    @staticmethod
    def _has_intervals(steps) -> bool:

        for step in steps or []:

            if getattr(step, "kind", None) == INTERVAL:

                return True

            if ExecutionLog._has_intervals(getattr(step, "steps", None)):

                return True

        return False

    @staticmethod
    def _range(fast: str | None, slow: str | None) -> str | None:

        return f"{fast}-{slow}" if fast and slow else None

    @staticmethod
    def _dist(meters: float) -> str:

        return f"{meters / 1000:.1f} km" if meters >= 1000 else f"{meters:.0f} m"

    @staticmethod
    def _sec(pace: str | None) -> int | None:

        if not pace or ":" not in str(pace):

            return None

        try:

            minutes, seconds = str(pace).split(":")

            return int(minutes) * 60 + int(seconds)

        except (TypeError, ValueError):

            return None
