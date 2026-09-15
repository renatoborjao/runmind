"""Conclusão do onboarding pelo WIZARD do app (self-cadastro). Recebe os dados
já estruturados (o app coleta em campos/botões, não em conversa), grava o perfil
com o MESMO mapa do bot (`OnboardingFlow._finalize`) e gera o plano inicial pelo
miolo compartilhado (`ensure_initial_plan`). Não encosta no fluxo do Telegram.

O perfil já existe como esqueleto (criado no cadastro, `onboarding_complete`
False) — aqui a gente preenche de verdade e marca como completo.
"""

from __future__ import annotations

from app.application.onboarding.initial_plan import ensure_initial_plan
from app.core.weekdays import WEEKDAYS
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class OnboardingValidationError(ValueError):
    """Dado do wizard fora da faixa aceita (o endpoint vira 422)."""


def _days_from_indices(indices: list[int]) -> list[str]:
    """[1,3,5] -> ["Tuesday","Thursday","Saturday"] (nomes internos em inglês),
    sem repetição e na ordem recebida."""

    out: list[str] = []

    for i in indices or []:

        name = WEEKDAYS.get(i)

        if name and name not in out:

            out.append(name)

    return out


class AppOnboardingService:

    @staticmethod
    async def complete(slug: str, data: dict) -> dict:
        """Finaliza o cadastro do atleta `slug` com os dados do wizard. Devolve
        um resumo pro app (`{"ok": True, "goal": ...}`). Levanta
        `OnboardingValidationError` se algum dado essencial está fora da faixa."""

        repo = RunnerProfileRepository()

        # ------- validação (mesmas faixas do OnboardingFlow) -------
        name = (data.get("name") or "").strip()

        if not name:

            raise OnboardingValidationError("nome obrigatório")

        age = data.get("age")

        if not (isinstance(age, int) and 10 <= age <= 100):

            raise OnboardingValidationError("idade inválida")

        sex = data.get("sex")

        if sex not in ("M", "F", None):

            raise OnboardingValidationError("sexo inválido")

        weight = data.get("weight")

        if not (isinstance(weight, (int, float)) and 30 <= weight <= 250):

            raise OnboardingValidationError("peso inválido")

        height = data.get("height")

        if isinstance(height, (int, float)) and height > 3:  # veio em cm

            height = height / 100

        if not (isinstance(height, (int, float)) and 1.2 <= height <= 2.3):

            raise OnboardingValidationError("altura inválida")

        days = _days_from_indices(data.get("days") or [])

        if not days:

            raise OnboardingValidationError("escolha ao menos um dia")

        goal = (data.get("goal") or "").strip()

        if not goal:

            raise OnboardingValidationError("objetivo obrigatório")

        # ------- experiência (dois caminhos, como no bot) -------
        runs_today = bool(data.get("runs_today"))

        runs_per_week = None

        typical_km = None

        initial_pace_min_km = None

        mobility = None

        continuous_run_minutes = None

        walk_pace_min_km = None

        if runs_today:

            rpw = data.get("runs_per_week")

            if isinstance(rpw, int) and 1 <= rpw <= 7:

                runs_per_week = rpw

            tk = data.get("typical_km")

            if isinstance(tk, (int, float)) and 0 < tk <= 50:

                typical_km = float(tk)

            # pace vem de um treino concreto (km + minutos) — sem média ambígua
            dist = data.get("pace_distance_km")

            mins = data.get("pace_minutes")

            if (
                isinstance(dist, (int, float))
                and 0 < dist <= 50
                and isinstance(mins, (int, float))
                and mins > 0
            ):

                pace = mins / dist

                if 2 <= pace <= 20:

                    initial_pace_min_km = round(pace, 2)

        else:

            mob = data.get("mobility")

            mobility = mob if mob in ("walker", "run_walker", "runner") else "walker"

            crm = data.get("continuous_run_minutes")

            if isinstance(crm, (int, float)) and 0 < crm <= 60:

                continuous_run_minutes = float(crm)

            kmh = data.get("walk_speed_kmh")

            if isinstance(kmh, (int, float)) and 2 <= kmh <= 8:

                walk_pace_min_km = round(60 / kmh, 2)

        initial_weekly_km = (
            round(typical_km * runs_per_week, 1)
            if typical_km and runs_per_week
            else None
        )

        external_coach = bool(data.get("external_coach"))

        # ------- grava (merge no esqueleto: preserva email/channel/id) -------
        repo.update_fields(
            slug,
            {
                "name": name,
                "age": age,
                "sex": sex,
                "weight": float(weight),
                "height": round(float(height), 2),
                "goal": goal,
                "weekly_training_days": len(days),
                "preferred_running_days": days,
                "strength_training_days": [],
                "target_race": data.get("target_race"),
                "target_time": data.get("target_time"),
                "race_date": data.get("race_date"),
                "initial_pace_min_km": initial_pace_min_km,
                "initial_weekly_km": initial_weekly_km,
                "mobility": mobility,
                "continuous_run_minutes": continuous_run_minutes,
                "walk_pace_min_km": walk_pace_min_km,
                "external_coach": external_coach,
                "notifications": True,
                "onboarding_complete": True,
            },
        )

        # ------- plano inicial (mesmo miolo do bot) -------
        # com treinador externo, não gera plano próprio (ele manda o dele depois)
        if not external_coach:

            try:

                await ensure_initial_plan(slug, start_next_week=False)

            except Exception as e:  # nunca deixa o cadastro falhar por causa do plano

                print(f"Falha ao gerar plano inicial no onboarding do app ({slug}): {e}")

        return {"ok": True, "goal": goal, "external_coach": external_coach}
