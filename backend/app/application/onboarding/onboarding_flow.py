import unicodedata
from datetime import UTC, datetime, timedelta

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.coach.planning.plan_realism_reviewer import (
    PlanRealismReviewer,
)
from app.application.external_plan.external_plan_extraction_engine import (
    ExternalPlanExtractionEngine,
)
from app.application.external_plan.external_plan_service import (
    ExternalPlanService,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.onboarding.onboarding_answer_parser import (
    OnboardingAnswerParser,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS, weekday_label
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.integrations.media_download import (
    download_media,
)
from app.infrastructure.persistence.onboarding_state_repository import (
    OnboardingStateRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.storage.token_store import TokenStore

RETRY_PREFIX = "Desculpa, não consegui entender. "

BUSY_REPLY = (
    "Opa, me embananei aqui por um instante 😅 "
    "Me manda sua última mensagem de novo?"
)

QUESTIONS = {
    "ASK_NAME": (
        "Oi! 👋 Eu sou o coach do RunMind — vou montar e acompanhar "
        "seus treinos de corrida por aqui.\n\n"
        "Pra começar: como você se chama?"
    ),
    "ASK_AGE": (
        "Prazer, {name}! 🙌\n\n"
        "Quantos anos você tem?"
    ),
    "ASK_WEIGHT": (
        "E quanto você pesa? (em kg)"
    ),
    "ASK_HEIGHT": (
        "Qual a sua altura? (ex: 1,78 m)"
    ),
    "ASK_STRAVA": (
        "Você já tem conta no Strava? (sim/não)\n\n"
        "É por ele que eu recebo seus treinos e te dou feedback — "
        "então essa parte é obrigatória, mas a conta é gratuita. 😉"
    ),
    "ASK_RUNS_TODAY": (
        "Você já corre hoje? (sim/não)"
    ),
    "ASK_RUNS_PER_WEEK": (
        "Show! Quantas vezes por semana você costuma correr?"
    ),
    "ASK_TYPICAL_KM": (
        "E quantos km, mais ou menos, em cada treino?"
    ),
    "ASK_MOVEMENT": (
        "Massa que quer começar! 🙌\n\n"
        "Me conta como você se movimenta hoje: você caminha, faz um "
        "trote leve, ou intercala os dois? E por quanto tempo aguenta?\n\n"
        "(ex: \"caminho 30 min\" ou \"trote 1 min e caminho 3 min\")"
    ),
    "ASK_COACH": (
        "Você já treina com um treinador ou segue uma planilha de "
        "treinos? (sim/não)"
    ),
    "AWAIT_PLAN_MEDIA": (
        "Então me manda um print, foto ou PDF do seu treino desta "
        "semana 📸 — eu registro e acompanho os treinos do seu "
        "treinador, sem mudar nada.\n\n"
        "(se não tiver em mãos agora, responde \"mando depois\")"
    ),
    "ASK_PACE": (
        "E em quanto tempo você costuma fazer esses {typical_km:.0f} km?"
    ),
    "ASK_DAYS": (
        "Quais dias da semana você pode correr? "
        "(ex: terça, quinta e sábado)"
    ),
    "ASK_GOAL": (
        "Qual seu objetivo? Pode ser uma prova ou marca "
        "(ex: \"correr 10 km em 55 minutos\") ou simplesmente saúde."
    ),
}


class OnboardingFlow:

    @staticmethod
    async def handle(
        channel: str,
        address: str,
        incoming_text: str,
        sender_name: str = "",
        media: dict | None = None,
    ) -> str:

        repo = OnboardingStateRepository()

        state = repo.load(address)

        # primeira mensagem: só dá boas-vindas e pergunta o nome
        if state is None:

            state = {
                "step": "ASK_NAME",
                "answers": {},
                "channel": channel,
                "address": address,
                "created_at": datetime.now(UTC).isoformat(),
            }

            repo.save(address, state)

            return QUESTIONS["ASK_NAME"]

        step = state["step"]

        # mídia só é aceita no passo do plano do treinador
        if media is not None:

            if step == "AWAIT_PLAN_MEDIA":

                return await OnboardingFlow._on_plan_media(
                    address,
                    state,
                    media,
                    repo,
                )

            return (
                "Boa! Mas primeiro vamos terminar seu cadastro. 😉 "
                + OnboardingFlow._question(state)
            )

        # indisponibilidade do Gemini (ex: rate limit do nível
        # gratuito) não pode virar 500: pede pra reenviar
        try:

            parsed = await OnboardingAnswerParser.parse(
                step=step,
                question=OnboardingFlow._question(state),
                answer=incoming_text,
            )

        except Exception as e:

            print(f"Falha no parser do onboarding ({step}): {e}")

            return BUSY_REPLY

        handler = getattr(
            OnboardingFlow,
            f"_on_{step.lower()}",
        )

        reply = await handler(address, state, parsed, repo)

        return reply

    # ==========================================================
    # Passos
    # ==========================================================

    @staticmethod
    async def _on_ask_name(address, state, parsed, repo) -> str:

        name = (parsed.get("name") or "").strip()

        if not name:

            return RETRY_PREFIX + QUESTIONS["ASK_NAME"]

        state["answers"]["name"] = name

        state["slug"] = OnboardingFlow._unique_slug(name)

        state["step"] = "ASK_AGE"

        repo.save(address, state)

        return QUESTIONS["ASK_AGE"].format(name=name)

    @staticmethod
    async def _on_ask_age(address, state, parsed, repo) -> str:

        age = parsed.get("age")

        if not (isinstance(age, int) and 10 <= age <= 100):

            return RETRY_PREFIX + QUESTIONS["ASK_AGE"].format(
                name=state["answers"]["name"],
            )

        state["answers"]["age"] = age

        state["step"] = "ASK_WEIGHT"

        repo.save(address, state)

        return QUESTIONS["ASK_WEIGHT"]

    @staticmethod
    async def _on_ask_weight(address, state, parsed, repo) -> str:

        weight = parsed.get("weight")

        if not (isinstance(weight, (int, float)) and 30 <= weight <= 250):

            return RETRY_PREFIX + QUESTIONS["ASK_WEIGHT"]

        state["answers"]["weight"] = float(weight)

        state["step"] = "ASK_HEIGHT"

        repo.save(address, state)

        return QUESTIONS["ASK_HEIGHT"]

    @staticmethod
    async def _on_ask_height(address, state, parsed, repo) -> str:

        height = parsed.get("height")

        # altura em cm por engano do parser (ex: 178 -> 1.78)
        if isinstance(height, (int, float)) and height > 3:

            height = height / 100

        if not (isinstance(height, (int, float)) and 1.2 <= height <= 2.3):

            return RETRY_PREFIX + QUESTIONS["ASK_HEIGHT"]

        state["answers"]["height"] = round(float(height), 2)

        state["step"] = "ASK_STRAVA"

        repo.save(address, state)

        return QUESTIONS["ASK_STRAVA"]

    @staticmethod
    async def _on_ask_strava(address, state, parsed, repo) -> str:

        has_strava = parsed.get("has_strava")

        if not isinstance(has_strava, bool):

            return RETRY_PREFIX + QUESTIONS["ASK_STRAVA"]

        state["answers"]["has_strava"] = has_strava

        state["step"] = "ASK_RUNS_TODAY"

        repo.save(address, state)

        link = OnboardingFlow._connect_link(state)

        if has_strava:

            return (
                "Ótimo! Conecta seu Strava neste link (pode fazer "
                f"depois, com calma):\n{link}\n\n"
                "Enquanto isso, seguimos por aqui. "
                + QUESTIONS["ASK_RUNS_TODAY"]
            )

        # Strava é obrigatório: quem não tem cria a conta gratuita
        return (
            "Sem problema! Baixa o app do Strava (gratuito) e cria "
            "sua conta — é rapidinho. Depois conecta comigo neste "
            f"link:\n{link}\n\n"
            "Enquanto isso, seguimos por aqui. "
            + QUESTIONS["ASK_RUNS_TODAY"]
        )

    @staticmethod
    async def _on_ask_runs_today(address, state, parsed, repo) -> str:

        runs_today = parsed.get("runs_today")

        if not isinstance(runs_today, bool):

            return RETRY_PREFIX + QUESTIONS["ASK_RUNS_TODAY"]

        state["answers"]["runs_today"] = runs_today

        # já corre: pergunta frequência e distância, uma de cada vez
        if runs_today:

            state["step"] = "ASK_RUNS_PER_WEEK"

            repo.save(address, state)

            return QUESTIONS["ASK_RUNS_PER_WEEK"]

        # ainda não corre: capta como ele se move hoje (base do run/walk)
        state["step"] = "ASK_MOVEMENT"

        repo.save(address, state)

        return QUESTIONS["ASK_MOVEMENT"]

    @staticmethod
    async def _on_ask_movement(address, state, parsed, repo) -> str:

        # passo opcional de capacidade: sempre avança (default seguro é
        # caminhante) — não trava o cadastro se a extração vier pobre.
        mobility = parsed.get("mobility")

        if mobility not in ("walker", "run_walker", "runner"):

            mobility = "walker"

        state["answers"]["mobility"] = mobility

        crm = parsed.get("continuous_run_minutes")

        if isinstance(crm, (int, float)) and 0 < crm <= 60:

            state["answers"]["continuous_run_minutes"] = float(crm)

        kmh = parsed.get("walk_speed_kmh")

        if isinstance(kmh, (int, float)) and 2 <= kmh <= 8:

            state["answers"]["walk_pace_min_km"] = round(60 / kmh, 2)

        state["step"] = "ASK_DAYS"

        repo.save(address, state)

        return QUESTIONS["ASK_DAYS"]

    @staticmethod
    async def _on_ask_runs_per_week(address, state, parsed, repo) -> str:

        runs_per_week = parsed.get("runs_per_week")

        if not (isinstance(runs_per_week, int) and 1 <= runs_per_week <= 7):

            return RETRY_PREFIX + QUESTIONS["ASK_RUNS_PER_WEEK"]

        state["answers"]["runs_per_week"] = runs_per_week

        state["step"] = "ASK_TYPICAL_KM"

        repo.save(address, state)

        return QUESTIONS["ASK_TYPICAL_KM"]

    @staticmethod
    async def _on_ask_typical_km(address, state, parsed, repo) -> str:

        typical_km = parsed.get("typical_km")

        if not (isinstance(typical_km, (int, float)) and 0 < typical_km <= 50):

            return RETRY_PREFIX + QUESTIONS["ASK_TYPICAL_KM"]

        state["answers"]["typical_km"] = float(typical_km)

        # quem já corre pode ter treinador
        state["step"] = "ASK_COACH"

        repo.save(address, state)

        return QUESTIONS["ASK_COACH"]

    @staticmethod
    async def _on_ask_coach(address, state, parsed, repo) -> str:

        has_coach = parsed.get("has_coach")

        if not isinstance(has_coach, bool):

            return RETRY_PREFIX + QUESTIONS["ASK_COACH"]

        state["answers"]["has_coach"] = has_coach

        # pace declarado vale para os dois caminhos (fallback de
        # métricas até o histórico do Strava chegar)
        state["step"] = "ASK_PACE"

        repo.save(address, state)

        return QUESTIONS["ASK_PACE"].format(
            typical_km=state["answers"]["typical_km"],
        )

    @staticmethod
    async def _on_ask_pace(address, state, parsed, repo) -> str:

        minutes = parsed.get("typical_minutes")

        typical_km = state["answers"]["typical_km"]

        if not isinstance(minutes, (int, float)) or minutes <= 0:

            return RETRY_PREFIX + QUESTIONS["ASK_PACE"].format(
                typical_km=typical_km,
            )

        pace = minutes / typical_km

        # pace fora da realidade (2:00 a 20:00 min/km)
        if not 2 <= pace <= 20:

            return RETRY_PREFIX + QUESTIONS["ASK_PACE"].format(
                typical_km=typical_km,
            )

        state["answers"]["initial_pace_min_km"] = round(pace, 2)

        state["step"] = "ASK_DAYS"

        repo.save(address, state)

        return QUESTIONS["ASK_DAYS"]

    @staticmethod
    async def _on_ask_days(address, state, parsed, repo) -> str:

        raw_days = parsed.get("days") or []

        valid_names = set(WEEKDAYS.values())

        days = []

        for day in raw_days:

            if isinstance(day, str) and day in valid_names:

                if day not in days:

                    days.append(day)

        if not days:

            return RETRY_PREFIX + QUESTIONS["ASK_DAYS"]

        state["answers"]["days"] = days

        state["step"] = "ASK_GOAL"

        repo.save(address, state)

        return QUESTIONS["ASK_GOAL"]

    @staticmethod
    async def _on_ask_goal(address, state, parsed, repo) -> str:

        goal = (parsed.get("goal") or "").strip()

        if not goal:

            return RETRY_PREFIX + QUESTIONS["ASK_GOAL"]

        state["answers"].update(
            goal=goal,
            target_race=parsed.get("target_race"),
            target_time=parsed.get("target_time"),
            race_date=OnboardingFlow._valid_iso_date(
                parsed.get("race_date"),
            ),
        )

        # com treinador: pede o plano da semana antes de confirmar
        if state["answers"].get("has_coach"):

            state["step"] = "AWAIT_PLAN_MEDIA"

            repo.save(address, state)

            return QUESTIONS["AWAIT_PLAN_MEDIA"]

        state["step"] = "CONFIRM"

        repo.save(address, state)

        return OnboardingFlow._summary(state)

    @staticmethod
    async def _on_await_plan_media(address, state, parsed, repo) -> str:

        # resposta em texto neste passo: só aceita "mando depois"
        if parsed.get("skip") is True:

            state["step"] = "CONFIRM"

            repo.save(address, state)

            return OnboardingFlow._summary(state)

        return (
            "Sem pressa! Quando tiver o print em mãos é só mandar. "
            + QUESTIONS["AWAIT_PLAN_MEDIA"]
        )

    @staticmethod
    async def _on_plan_media(address, state, media, repo) -> str:

        try:

            media_bytes, mimetype = await download_media(
                state["channel"],
                media,
            )

            sessions = await ExternalPlanExtractionEngine.extract(
                media_bytes,
                media.get("mimetype") or mimetype,
            )

        except Exception as e:

            print(f"Falha ao processar mídia do onboarding: {e}")

            return BUSY_REPLY

        if not sessions:

            return (
                "Hmm, não consegui ler o treino nessa imagem. 😕 "
                "Consegue mandar uma foto mais nítida (ou o PDF)?"
            )

        state["answers"]["external_sessions"] = sessions

        state["step"] = "CONFIRM"

        repo.save(address, state)

        return OnboardingFlow._summary(state)

    @staticmethod
    async def _on_confirm(address, state, parsed, repo) -> str:

        confirmed = parsed.get("confirmed")

        if confirmed is False:

            repo.delete(address)

            return (
                "Sem problema! Se quiser recomeçar o cadastro, "
                "é só mandar outra mensagem. 👍"
            )

        if confirmed is not True:

            return (
                "Só confirmando: posso montar seu plano com esses "
                "dados? (sim/não)"
            )

        return await OnboardingFlow._finalize(address, state, repo)

    # ==========================================================
    # Conclusão
    # ==========================================================

    @staticmethod
    async def _finalize(address, state, repo) -> str:

        answers = state["answers"]

        slug = state["slug"]

        typical_km = answers.get("typical_km")

        runs_per_week = answers.get("runs_per_week")

        initial_weekly_km = (
            round(typical_km * runs_per_week, 1)
            if typical_km and runs_per_week
            else None
        )

        has_coach = bool(answers.get("has_coach"))

        channel = state["channel"]

        RunnerProfileRepository().save(
            slug,
            {
                "id": slug,
                "name": answers["name"],
                "age": answers["age"],
                "weight": answers["weight"],
                "height": answers["height"],
                "channel": channel,
                "phone": address if channel == "whatsapp" else "",
                "telegram_id": address if channel == "telegram" else None,
                "goal": answers["goal"],
                "weekly_training_days": len(answers["days"]),
                "preferred_running_days": answers["days"],
                "strength_training_days": [],
                "target_race": answers.get("target_race"),
                "target_time": answers.get("target_time"),
                "race_date": answers.get("race_date"),
                "strava_athlete_id": state.get("strava_athlete_id"),
                "injuries": [],
                "initial_pace_min_km": answers.get(
                    "initial_pace_min_km"
                ),
                "initial_weekly_km": initial_weekly_km,
                "mobility": answers.get("mobility"),
                "continuous_run_minutes": answers.get(
                    "continuous_run_minutes"
                ),
                "walk_pace_min_km": answers.get("walk_pace_min_km"),
                "external_coach": has_coach,
                "notifications": True,
                "timezone": "America/Sao_Paulo",
                "language": "pt-BR",
            },
        )

        # Com treinador: registra o plano do treinador e conclui.
        if has_coach:

            plan_message = OnboardingFlow._register_external_plan(
                slug,
                answers,
            )

            return OnboardingFlow._finish(address, state, plan_message, repo)

        # Plano gerado pelo RunMind: se ainda dá tempo nesta semana,
        # pergunta se começa agora ou na próxima; se está no fim da
        # semana, já monta pra próxima (datas sempre futuras).
        today = today_local()

        days = answers["days"]

        if OnboardingFlow._should_ask_week(days, today):

            state["week_labels"] = OnboardingFlow._remaining_day_labels(
                days,
                today,
            )

            state["step"] = "ASK_WEEK_CHOICE"

            repo.save(address, state)

            return OnboardingFlow._week_choice_question(
                answers["name"],
                state["week_labels"],
            )

        plan_message = await OnboardingFlow._build_plan_message(
            slug,
            start_next_week=True,
        )

        return OnboardingFlow._finish(address, state, plan_message, repo)

    @staticmethod
    async def _on_ask_week_choice(address, state, parsed, repo) -> str:

        start = parsed.get("start_week")

        if start not in ("current", "next"):

            return RETRY_PREFIX + OnboardingFlow._week_choice_question(
                state["answers"]["name"],
                state.get("week_labels", []),
            )

        plan_message = await OnboardingFlow._build_plan_message(
            state["slug"],
            start_next_week=(start == "next"),
        )

        return OnboardingFlow._finish(address, state, plan_message, repo)

    @staticmethod
    def _finish(address, state, plan_message, repo) -> str:
        """Mensagem final do cadastro (comum aos caminhos treinador,
        próxima-semana e escolha do atleta)."""

        answers = state["answers"]

        slug = state["slug"]

        repo.delete(address)

        strava_reminder = ""

        if TokenStore(slug).load() is None:

            strava_reminder = (
                "\n\n⚠️ Falta só uma coisa: conectar seu Strava — é "
                "por ele que eu acompanho seus treinos e te dou "
                "feedback. Conecta aqui:\n"
                f"{OnboardingFlow._connect_link(state)}"
            )

        return (
            f"Cadastro feito, {answers['name']}! 🎉\n\n"
            f"{plan_message}\n\n"
            "A partir de agora é comigo: te mando o plano todo domingo, "
            "o resumo da semana, e a cada treino registrado você recebe "
            "meu feedback. Qualquer coisa, é só chamar!"
            f"{strava_reminder}"
        )

    # ==========================================================
    # Escolha da semana de início (esta vs próxima)
    # ==========================================================

    @staticmethod
    def _remaining_day_labels(
        preferred_days: list[str],
        today,
    ) -> list[str]:
        """Rótulos pt-BR dos dias de treino que ainda faltam NESTA semana
        (data >= hoje), na ordem escolhida pelo atleta."""

        monday = today - timedelta(days=today.weekday())

        index = {name.lower(): i for i, name in WEEKDAYS.items()}

        labels = []

        for day in preferred_days:

            i = index.get(day.lower())

            if i is not None and (monday + timedelta(days=i)) >= today:

                labels.append(weekday_label(day))

        return labels

    @staticmethod
    def _should_ask_week(
        preferred_days: list[str],
        today,
    ) -> bool:
        """Pergunta esta/próxima só quando ainda restam 2+ dias de treino
        nesta semana; com menos que isso, vai direto pra próxima."""

        return len(
            OnboardingFlow._remaining_day_labels(preferred_days, today)
        ) >= 2

    @staticmethod
    def _week_choice_question(
        name: str,
        labels: list[str],
    ) -> str:

        if len(labels) <= 2:

            days_txt = " e ".join(labels)

        else:

            days_txt = ", ".join(labels[:-1]) + " e " + labels[-1]

        return (
            f"Boa, {name}! Última pergunta pra fechar 👇\n\n"
            f"Quer começar já *nesta semana* (ainda dá pra treinar "
            f"{days_txt}) ou prefere começar *na próxima segunda*, com a "
            "semana cheia?\n\n"
            "(responde \"esta\" ou \"próxima\")"
        )

    @staticmethod
    def _register_external_plan(slug: str, answers: dict) -> str:

        sessions = answers.get("external_sessions")

        if not sessions:

            return (
                "Quando tiver o treino do seu treinador em mãos, me "
                "manda o print/foto/PDF que eu registro e começo a "
                "acompanhar. 📸"
            )

        runner = RunnerProfileRepository().load(slug)

        plan = ExternalPlanService.apply(slug, runner, sessions)

        if plan is None:

            return (
                "Não consegui aproveitar as sessões do plano — me "
                "manda o print de novo depois que eu registro. 📸"
            )

        sessions_block = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(plan),
        )

        return (
            "Plano do seu treinador registrado! ✅\n\n"
            f"{sessions_block}\n\n"
            "Vou acompanhar esses treinos, sem mudar nada — o plano "
            "é do seu treinador."
        )

    @staticmethod
    async def _build_plan_message(
        slug: str,
        start_next_week: bool = False,
    ) -> str:

        repository = RunnerProfileRepository()

        runner = repository.load(slug)

        try:

            history = await LoadTrainingHistory.execute(
                profile=slug,
            )

        except Exception:

            # sem Strava conectado ainda: plano inicial conservador
            history = TrainingHistory(activities=[])

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = MetricsResolver.resolve(
            runner,
            history,
        )

        goal = BuildTrainingGoal.execute(runner)

        today = today_local()

        if start_next_week:

            monday = today - timedelta(days=today.weekday())

            reference_date = monday + timedelta(days=7)

        else:

            reference_date = today

        plan = WeeklyPlanService.get_or_generate(
            profile=slug,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            reference_date=reference_date,
            history=history,
        )

        # IA revisora do primeiro plano: sinaliza qualquer sessão irreal
        # pra este atleta antes de mostrar (fallback = plano intacto).
        plan = await PlanRealismReviewer.ensure_reviewed(
            slug,
            runner,
            plan,
        )

        # dias já passados desta semana ficam marcados como "já passou"
        # (não realizado) — nada de data passada como se fosse fazer
        sessions_text = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(
                plan,
                reference_date=today,
                past_label="⏭️ (já passou)",
            )
        ).strip()

        if start_next_week:

            header = (
                "🗓️ Seu plano já está pronto, começando na "
                "próxima segunda:"
            )

        else:

            header = (
                "🏃 Seu plano desta semana (o que já passou "
                "fica marcado):"
            )

        return f"{header}\n\n{sessions_text}"

    # ==========================================================
    # Auxiliares
    # ==========================================================

    @staticmethod
    def _question(state: dict) -> str:

        step = state["step"]

        if step == "CONFIRM":

            return OnboardingFlow._summary(state)

        if step == "ASK_WEEK_CHOICE":

            return OnboardingFlow._week_choice_question(
                state["answers"].get("name", ""),
                state.get("week_labels", []),
            )

        template = QUESTIONS[step]

        answers = state["answers"]

        if step == "ASK_AGE":

            return template.format(name=answers.get("name", ""))

        if step == "ASK_PACE":

            return template.format(
                typical_km=answers.get("typical_km", 0),
            )

        return template

    @staticmethod
    def _summary(state: dict) -> str:

        answers = state["answers"]

        days = ", ".join(
            weekday_label(day) for day in answers["days"]
        )

        experience = "ainda não corre"

        if answers.get("runs_today"):

            experience = (
                f"corre {answers['runs_per_week']}x/semana, "
                f"~{answers['typical_km']:.0f} km por treino"
            )

        elif answers.get("mobility") == "run_walker":

            experience = "ainda não corre — hoje faz trote e caminhada"

        elif answers.get("mobility") == "walker":

            experience = "ainda não corre — hoje caminha"

        coach_line = ""

        if answers.get("has_coach"):

            sessions = answers.get("external_sessions")

            plan_status = (
                f"plano da semana recebido "
                f"({len(sessions)} treinos)"
                if sessions
                else "vai mandar o plano depois"
            )

            coach_line = (
                f"• Treinador: sim — {plan_status}\n"
            )

        question = (
            "Posso registrar seu cadastro e acompanhar os treinos "
            "do seu treinador? (sim/não)"
            if answers.get("has_coach")
            else "Posso montar seu plano com esses dados? (sim/não)"
        )

        return (
            "Fechou! Confere se está tudo certo:\n\n"
            f"• Nome: {answers['name']}\n"
            f"• Idade: {answers['age']} anos — "
            f"{answers['weight']:.0f} kg, {answers['height']:.2f} m\n"
            f"• Experiência: {experience}\n"
            f"{coach_line}"
            f"• Dias de corrida: {days}\n"
            f"• Objetivo: {answers['goal']}\n\n"
            f"{question}"
        )

    @staticmethod
    def _valid_iso_date(value) -> str | None:

        if not isinstance(value, str):

            return None

        try:

            datetime.fromisoformat(value)

        except ValueError:

            return None

        return value

    # prefixo do canal no `state` do OAuth, pra o callback saber por
    # onde resolver o atleta (tg:<chat_id> ou wa:<telefone>)
    _CHANNEL_PREFIX = {"telegram": "tg", "whatsapp": "wa"}

    @staticmethod
    def _connect_link(state: dict) -> str:

        settings = get_settings()

        prefix = OnboardingFlow._CHANNEL_PREFIX.get(
            state["channel"],
            "wa",
        )

        oauth_state = f"{prefix}:{state['address']}"

        return (
            f"{settings.public_base_url}"
            f"/api/v1/strava/connect?state={oauth_state}"
        )

    @staticmethod
    def _unique_slug(name: str) -> str:

        normalized = unicodedata.normalize("NFKD", name.lower())

        slug = "".join(
            char
            for char in normalized
            if char.isalnum()
        )

        slug = slug or "corredor"

        repository = RunnerProfileRepository()

        existing = set(repository.list_all())

        if slug not in existing:

            return slug

        suffix = 2

        while f"{slug}{suffix}" in existing:

            suffix += 1

        return f"{slug}{suffix}"
