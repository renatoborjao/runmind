"""Executa a ação `goal` do CoachBrain com os fatos JÁ ESTRUTURADOS (sem
re-parsear texto comprimido). As "mãos" determinísticas da meta/prova:

- REGISTRA sempre a prova/meta na memória evolutiva (nada se perde);
- ÂNCORA = prova datada MAIS PRÓXIMA — nunca deixa uma prova mais distante
  atropelar uma âncora mais perto (o bug do _apply_concrete_goal);
- PRESERVA o objetivo-mãe (norte): stepping_stone/additional não mexem no
  `goal`; replace/primary atualizam;
- grava a HIERARQUIA (degrau × norte) como memória, pra o gerador periodizar
  o degrau rumo ao norte;
- só REGENERA a semana quando a âncora muda E está perto o bastante pra afetar
  a semana atual (pico/afiação); senão só registra e a regeração de domingo
  mira a nova prova, sem bagunçar o relógio no meio da semana.

Atrás da flag goal_brain (fallback = GoalChangeApplier de sempre). O texto que
lidera a resposta é a VOZ do coach (o `say` do cérebro); o executor só anexa o
plano regerado + oferta de relógio quando de fato regenerou.
Ver [[project_multiplos_objetivos]] e [[feedback_nao_tapar_sol_com_peneira]]."""

from dataclasses import dataclass
from datetime import date

from app.application.coach.conversation.coach_brain import BrainAction
from app.application.coach.memory.runner_memory_service import RunnerMemoryService
from app.application.garmin.watch_offer import watch_update_offer
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# nota de hierarquia por relação — a inteligência que o gerador de plano lê pra
# periodizar (afiar o degrau sem largar o norte).
_RELATIONSHIP_NOTE = {
    "primary": "é a meta PRINCIPAL (norte) do atleta.",
    "stepping_stone": (
        "é um DEGRAU rumo à meta maior — afiar pra ela SEM comprometer a base "
        "aeróbica/longão de longo prazo que o objetivo-mãe exige."
    ),
    "additional": "é uma meta somada às que já tem (objetivos concorrentes).",
    "replace": "passou a ser o objetivo atual (troca o anterior).",
}


@dataclass(slots=True)
class _GoalOutcome:

    action: BrainAction

    relationship: str

    anchor_changed: bool

    regen_due: bool  # âncora mudou E está na janela que afeta a semana atual


class GoalActionExecutor:

    # janela (dias) em que a mudança de âncora afeta a semana ATUAL o bastante
    # pra regenerar agora; além disso, só registra e deixa domingo mirar a prova
    # (sem bagunçar o relógio no meio da semana). Alinha com "regera a partir de
    # domingo, como sempre".
    _REGEN_WINDOW_DAYS = 21

    @staticmethod
    async def apply(
        profile: str,
        runner: RunnerProfile,
        action: BrainAction,
        say: str = "",
    ) -> str | None:
        """Uma meta/prova estruturada (atalho de apply_many com 1 ação)."""

        return await GoalActionExecutor.apply_many(
            profile, runner, [action], say,
        )

    @staticmethod
    async def apply_many(
        profile: str,
        runner: RunnerProfile,
        actions: list[BrainAction],
        say: str = "",
    ) -> str | None:
        """Aplica UMA OU VÁRIAS metas/provas da mesma mensagem (ex.: turno em
        que o atleta cita a meia como norte E a 15k como degrau). Registra cada
        uma, reancora na prova MAIS PRÓXIMA (independente da ordem) e regenera
        no MÁXIMO uma vez. None se nada era acionável (cai na fala/cascata)."""

        repo = RunnerProfileRepository()

        outcomes: list[_GoalOutcome] = []

        for action in actions:

            outcome = GoalActionExecutor._register_one(repo, profile, runner, action)

            if outcome is not None:

                outcomes.append(outcome)

        if not outcomes:

            return None

        lead = (say or "").strip()

        # treinador externo: não geramos plano (é do treinador dele)
        if runner.external_coach:

            return lead or "Anotado! 🎯"

        # regeração: no MÁXIMO uma, só se alguma âncora mudou dentro da janela
        if any(o.regen_due for o in outcomes):

            _, plan = await CurrentPlanProvider.for_profile(profile, force=True)

            plan_text = WeeklyPlanMessageFormatter.week_plan_message(
                runner.name, plan, profile=profile,
            )

            body = lead or f"Fechou, {runner.name}! Ajustei tua meta. 🎯"

            return (
                f"{body}\n\nComo a prova tá logo ali, já ajustei a semana pra "
                f"mirar ela:\n\n{plan_text}{watch_update_offer(profile)}"
            )

        return lead or GoalActionExecutor._default_confirm(runner, outcomes)

    # ==================================================================

    @staticmethod
    def _register_one(
        repo: RunnerProfileRepository,
        profile: str,
        runner: RunnerProfile,
        action: BrainAction,
    ) -> "_GoalOutcome | None":
        """Efeitos de estado de UMA meta/prova (memória + âncora + norte).
        Devolve o outcome, ou None se não havia nada acionável."""

        has_race = bool(action.race_date)

        goal_text = (action.instruction or "").strip()

        if not has_race and not goal_text:

            return None

        # default seguro da relação quando o cérebro não classificou
        relationship = action.relationship or (
            "primary" if has_race else "replace"
        )

        # 1) memória evolutiva — SEMPRE (nada se perde)
        GoalActionExecutor._remember(profile, action, relationship, goal_text)

        # 2) âncora: prova datada mais próxima (nunca atropelada por mais longe)
        anchor_changed = GoalActionExecutor._maybe_set_anchor(
            repo, profile, runner, action, relationship,
        )

        # 3) norte (goal): replace/primary atualizam; degrau/adicional preservam
        if relationship in ("replace", "primary") and goal_text:

            repo.update_fields(profile, {"goal": goal_text})

            runner.goal = goal_text  # snapshot coerente entre ações da mensagem

        regen_due = anchor_changed and GoalActionExecutor._within_regen_window(
            action.race_date
        )

        return _GoalOutcome(action, relationship, anchor_changed, regen_due)

    @staticmethod
    def _remember(
        profile: str, action: BrainAction, relationship: str, goal_text: str,
    ) -> None:
        """Grava a prova/meta + a nota de hierarquia na memória evolutiva."""

        if action.race_date:

            desc = "Prova"

            if action.race_name:

                desc += f": {action.race_name}"

            if action.distance_km:

                desc += f", {action.distance_km:g} km"

            desc += f", em {action.race_date}"

            if action.target_time:

                desc += f", tempo-alvo {action.target_time}"

            else:

                desc += ", sem tempo-alvo (completar bem)"

            note = _RELATIONSHIP_NOTE.get(relationship)

            if note:

                desc += f" — {note}"

            content = desc

        else:

            content = f"Objetivo: {goal_text}"

            if relationship == "additional":

                content = (
                    f"Objetivo adicional: {goal_text} (soma aos que já tem)."
                )

            elif relationship == "replace":

                content = f"Objetivo atual: {goal_text} (troca o anterior)."

        RunnerMemoryService.process(
            profile, {"add": [{"category": "objetivo", "content": content}]},
        )

    @staticmethod
    def _maybe_set_anchor(
        repo: RunnerProfileRepository,
        profile: str,
        runner: RunnerProfile,
        action: BrainAction,
        relationship: str,
    ) -> bool:
        """Seta a âncora (target_race/race_date/target_time) SÓ quando a prova
        nova é a mais próxima no futuro (ou não havia âncora / a antiga já
        passou / é uma troca explícita). Devolve True se a âncora mudou."""

        new_date = action.race_date

        if not new_date:

            return False

        today = today_local().isoformat()

        # prova que já passou não vira âncora
        if new_date < today:

            return False

        current = runner.race_date  # ISO str ou None

        current_passed = bool(current and current < today)

        should = (
            relationship == "replace"
            or not current
            or current_passed
            or new_date < current
        )

        if not should:

            return False

        updates: dict = {
            "race_date": new_date,
            # tempo-alvo DESTA prova; None (conclusão) limpa o herdado da antiga
            "target_time": action.target_time,
        }

        label = GoalActionExecutor._race_label(action)

        if label:

            updates["target_race"] = label

        repo.update_fields(profile, updates)

        # atualiza o snapshot em memória pra a PRÓXIMA ação da mesma mensagem
        # comparar contra esta âncora — assim a prova mais próxima vence
        # INDEPENDENTE da ordem em que o cérebro as listou.
        runner.race_date = new_date

        runner.target_time = action.target_time

        if label:

            runner.target_race = label

        return True

    @staticmethod
    def _race_label(action: BrainAction) -> str:
        """Rótulo da prova pro perfil — garante a DISTÂNCIA parseável no texto
        (o BuildTrainingGoal deriva a distância do target_race)."""

        name = (action.race_name or "").strip()

        if action.distance_km:

            km = f"{action.distance_km:g} km"

            return f"{name} ({km})" if name else km

        return name

    @staticmethod
    def _within_regen_window(race_date_iso: str | None) -> bool:

        if not race_date_iso:

            return False

        try:

            d = date.fromisoformat(race_date_iso)

        except ValueError:

            return False

        delta = (d - today_local()).days

        return 0 <= delta <= GoalActionExecutor._REGEN_WINDOW_DAYS

    @staticmethod
    def _default_confirm(
        runner: RunnerProfile,
        outcomes: "list[_GoalOutcome]",
    ) -> str:
        """Fallback de confirmação quando o cérebro não trouxe fala (raro).
        Considera a prova que virou âncora, se houver."""

        anchored = next(
            (o for o in outcomes if o.anchor_changed and o.action.race_date),
            None,
        )

        if anchored is not None:

            return (
                f"Anotado, {runner.name}! Registrei tua prova "
                f"({anchored.action.race_date}) e ela vira a âncora do teu "
                "plano — a regeração de domingo já nasce mirando ela. 🎯"
            )

        race = next((o for o in outcomes if o.action.race_date), None)

        if race is not None:

            return (
                f"Anotado, {runner.name}! Guardei tua prova "
                f"({race.action.race_date}) como meta futura; tua prova mais "
                "próxima segue ancorando o plano. 🎯"
            )

        return f"Anotado, {runner.name}! Registrei teu objetivo. 🎯"
