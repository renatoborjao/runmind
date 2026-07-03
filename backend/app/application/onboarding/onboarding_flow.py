import unicodedata
from datetime import UTC, datetime

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
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
from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS, weekday_label
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory
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
    "ASK_BODY": (
        "Prazer, {name}! 🙌\n\n"
        "Me conta sua idade, peso e altura (ex: 33 anos, 91 kg, 1,78 m)."
    ),
    "ASK_STRAVA": (
        "Você já tem conta no Strava? (sim/não)\n\n"
        "É por ele que eu recebo seus treinos e te dou feedback — "
        "então essa parte é obrigatória, mas a conta é gratuita. 😉"
    ),
    "ASK_EXPERIENCE": (
        "Você já corre hoje? Se sim, quantas vezes por semana e "
        "quantos km por treino, mais ou menos?"
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
        phone: str,
        incoming_text: str,
        sender_name: str = "",
    ) -> str:

        repo = OnboardingStateRepository()

        state = repo.load(phone)

        # primeira mensagem: só dá boas-vindas e pergunta o nome
        if state is None:

            state = {
                "step": "ASK_NAME",
                "answers": {},
                "created_at": datetime.now(UTC).isoformat(),
            }

            repo.save(phone, state)

            return QUESTIONS["ASK_NAME"]

        step = state["step"]

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

        reply = await handler(phone, state, parsed, repo)

        return reply

    # ==========================================================
    # Passos
    # ==========================================================

    @staticmethod
    async def _on_ask_name(phone, state, parsed, repo) -> str:

        name = (parsed.get("name") or "").strip()

        if not name:

            return RETRY_PREFIX + QUESTIONS["ASK_NAME"]

        state["answers"]["name"] = name

        state["slug"] = OnboardingFlow._unique_slug(name)

        state["step"] = "ASK_BODY"

        repo.save(phone, state)

        return QUESTIONS["ASK_BODY"].format(name=name)

    @staticmethod
    async def _on_ask_body(phone, state, parsed, repo) -> str:

        age = parsed.get("age")

        weight = parsed.get("weight")

        height = parsed.get("height")

        # altura em cm por engano do parser
        if isinstance(height, (int, float)) and height > 3:

            height = height / 100

        valid = (
            isinstance(age, int) and 10 <= age <= 100
            and isinstance(weight, (int, float)) and 30 <= weight <= 250
            and isinstance(height, (int, float)) and 1.2 <= height <= 2.3
        )

        if not valid:

            return RETRY_PREFIX + QUESTIONS["ASK_BODY"].format(
                name=state["answers"]["name"],
            )

        state["answers"].update(
            age=age,
            weight=float(weight),
            height=round(float(height), 2),
        )

        state["step"] = "ASK_STRAVA"

        repo.save(phone, state)

        return QUESTIONS["ASK_STRAVA"]

    @staticmethod
    async def _on_ask_strava(phone, state, parsed, repo) -> str:

        has_strava = parsed.get("has_strava")

        if not isinstance(has_strava, bool):

            return RETRY_PREFIX + QUESTIONS["ASK_STRAVA"]

        state["answers"]["has_strava"] = has_strava

        state["step"] = "ASK_EXPERIENCE"

        repo.save(phone, state)

        link = OnboardingFlow._connect_link(phone)

        if has_strava:

            return (
                "Ótimo! Conecta seu Strava neste link (pode fazer "
                f"depois, com calma):\n{link}\n\n"
                "Enquanto isso, seguimos por aqui. "
                + QUESTIONS["ASK_EXPERIENCE"]
            )

        # Strava é obrigatório: quem não tem cria a conta gratuita
        return (
            "Sem problema! Baixa o app do Strava (gratuito) e cria "
            "sua conta — é rapidinho. Depois conecta comigo neste "
            f"link:\n{link}\n\n"
            "Enquanto isso, seguimos por aqui. "
            + QUESTIONS["ASK_EXPERIENCE"]
        )

    @staticmethod
    async def _on_ask_experience(phone, state, parsed, repo) -> str:

        runs_today = parsed.get("runs_today")

        if not isinstance(runs_today, bool):

            return RETRY_PREFIX + QUESTIONS["ASK_EXPERIENCE"]

        state["answers"]["runs_today"] = runs_today

        if runs_today:

            runs_per_week = parsed.get("runs_per_week")

            typical_km = parsed.get("typical_km")

            valid = (
                isinstance(runs_per_week, int)
                and 1 <= runs_per_week <= 7
                and isinstance(typical_km, (int, float))
                and 0 < typical_km <= 50
            )

            if not valid:

                return RETRY_PREFIX + QUESTIONS["ASK_EXPERIENCE"]

            state["answers"].update(
                runs_per_week=runs_per_week,
                typical_km=float(typical_km),
            )

            # o pace declarado vale até o histórico do Strava chegar
            state["step"] = "ASK_PACE"

            repo.save(phone, state)

            return QUESTIONS["ASK_PACE"].format(
                typical_km=typical_km,
            )

        state["step"] = "ASK_DAYS"

        repo.save(phone, state)

        return QUESTIONS["ASK_DAYS"]

    @staticmethod
    async def _on_ask_pace(phone, state, parsed, repo) -> str:

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

        repo.save(phone, state)

        return QUESTIONS["ASK_DAYS"]

    @staticmethod
    async def _on_ask_days(phone, state, parsed, repo) -> str:

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

        repo.save(phone, state)

        return QUESTIONS["ASK_GOAL"]

    @staticmethod
    async def _on_ask_goal(phone, state, parsed, repo) -> str:

        goal = (parsed.get("goal") or "").strip()

        if not goal:

            return RETRY_PREFIX + QUESTIONS["ASK_GOAL"]

        state["answers"].update(
            goal=goal,
            target_race=parsed.get("target_race"),
            target_time=parsed.get("target_time"),
        )

        state["step"] = "CONFIRM"

        repo.save(phone, state)

        return OnboardingFlow._summary(state)

    @staticmethod
    async def _on_confirm(phone, state, parsed, repo) -> str:

        confirmed = parsed.get("confirmed")

        if confirmed is False:

            repo.delete(phone)

            return (
                "Sem problema! Se quiser recomeçar o cadastro, "
                "é só mandar outra mensagem. 👍"
            )

        if confirmed is not True:

            return (
                "Só confirmando: posso montar seu plano com esses "
                "dados? (sim/não)"
            )

        return await OnboardingFlow._finalize(phone, state, repo)

    # ==========================================================
    # Conclusão
    # ==========================================================

    @staticmethod
    async def _finalize(phone, state, repo) -> str:

        answers = state["answers"]

        slug = state["slug"]

        typical_km = answers.get("typical_km")

        runs_per_week = answers.get("runs_per_week")

        initial_weekly_km = (
            round(typical_km * runs_per_week, 1)
            if typical_km and runs_per_week
            else None
        )

        RunnerProfileRepository().save(
            slug,
            {
                "id": slug,
                "name": answers["name"],
                "age": answers["age"],
                "weight": answers["weight"],
                "height": answers["height"],
                "phone": phone,
                "goal": answers["goal"],
                "weekly_training_days": len(answers["days"]),
                "preferred_running_days": answers["days"],
                "strength_training_days": [],
                "target_race": answers.get("target_race"),
                "target_time": answers.get("target_time"),
                "strava_athlete_id": state.get("strava_athlete_id"),
                "injuries": [],
                "initial_pace_min_km": answers.get(
                    "initial_pace_min_km"
                ),
                "initial_weekly_km": initial_weekly_km,
                "notifications": True,
                "timezone": "America/Sao_Paulo",
                "language": "pt-BR",
            },
        )

        plan_message = await OnboardingFlow._build_plan_message(slug)

        repo.delete(phone)

        strava_reminder = ""

        if TokenStore(slug).load() is None:

            strava_reminder = (
                "\n\n⚠️ Falta só uma coisa: conectar seu Strava — é "
                "por ele que eu acompanho seus treinos e te dou "
                "feedback. Conecta aqui:\n"
                f"{OnboardingFlow._connect_link(phone)}"
            )

        return (
            f"Cadastro feito, {answers['name']}! 🎉\n\n"
            f"{plan_message}\n\n"
            "A partir de agora é comigo: te mando o plano todo domingo, "
            "o resumo da semana, e a cada treino registrado você recebe "
            "meu feedback. Qualquer coisa, é só chamar!"
            f"{strava_reminder}"
        )

    @staticmethod
    async def _build_plan_message(slug: str) -> str:

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

        goal = TrainingGoal(
            name=runner.goal,
            distance_km=10,
            target_time=runner.target_time,
            race_date=None,
        )

        plan = WeeklyPlanService.get_or_generate(
            profile=slug,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
        )

        return WeeklyPlanMessageFormatter.format(
            runner.name,
            plan,
        )

    # ==========================================================
    # Auxiliares
    # ==========================================================

    @staticmethod
    def _question(state: dict) -> str:

        step = state["step"]

        if step == "CONFIRM":

            return OnboardingFlow._summary(state)

        template = QUESTIONS[step]

        answers = state["answers"]

        if step == "ASK_BODY":

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

        return (
            "Fechou! Confere se está tudo certo:\n\n"
            f"• Nome: {answers['name']}\n"
            f"• Idade: {answers['age']} anos — "
            f"{answers['weight']:.0f} kg, {answers['height']:.2f} m\n"
            f"• Experiência: {experience}\n"
            f"• Dias de corrida: {days}\n"
            f"• Objetivo: {answers['goal']}\n\n"
            "Posso montar seu plano com esses dados? (sim/não)"
        )

    @staticmethod
    def _connect_link(phone: str) -> str:

        settings = get_settings()

        return (
            f"{settings.public_base_url}"
            f"/api/v1/strava/connect?state={phone}"
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
