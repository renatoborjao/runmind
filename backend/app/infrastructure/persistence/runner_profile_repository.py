import json
from dataclasses import fields
from pathlib import Path

from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.evolution.phone_normalizer import (
    PhoneNormalizer,
)


class RunnerProfileRepository:

    def __init__(self):

        # um arquivo por atleta: storage/profiles/{profile}.json
        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "profiles"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> RunnerProfile:

        file = self.storage / f"{profile}.json"

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        # ignora chaves do JSON que a entidade (ainda) não conhece
        known = {field.name for field in fields(RunnerProfile)}

        return RunnerProfile(**{
            key: value
            for key, value in data.items()
            if key in known
        })

    def exists(
        self,
        profile: str,
    ) -> bool:

        return (self.storage / f"{profile}.json").exists()

    def save(
        self,
        profile: str,
        data: dict,
    ) -> None:
        """Grava o JSON completo do perfil (criação de atleta novo)."""

        file = self.storage / f"{profile}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )

    def update_fields(
        self,
        profile: str,
        updates: dict,
    ) -> None:
        """Merge de campos no JSON existente, preservando chaves que a
        entidade não conhece (notifications, timezone...)."""

        file = self.storage / f"{profile}.json"

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        data.update(updates)

        self.save(profile, data)

    def update_injuries(
        self,
        profile: str,
        injuries: list[str],
    ) -> None:

        self.update_fields(
            profile,
            {"injuries": injuries},
        )

    def find_by_phone(
        self,
        phone: str,
    ) -> str | None:

        target = PhoneNormalizer.normalize(phone)

        for profile, runner in self._valid_profiles():

            if PhoneNormalizer.normalize(runner.phone) == target:

                return profile

        return None

    def find_by_email(
        self,
        email: str,
    ) -> str | None:
        """Perfil dono deste e-mail (case-insensitive). None se ninguém."""

        target = email.strip().lower()

        if not target:

            return None

        for profile, runner in self._valid_profiles():

            if runner.email and runner.email.strip().lower() == target:

                return profile

        return None

    def find_by_telegram_id(
        self,
        telegram_id: str,
    ) -> str | None:

        target = str(telegram_id)

        for profile, runner in self._valid_profiles():

            if runner.telegram_id and str(runner.telegram_id) == target:

                return profile

        return None

    def list_all(
        self,
    ) -> list[str]:

        return [
            profile
            for profile, _ in self._valid_profiles()
        ]

    def list_active(
        self,
    ) -> list[str]:
        """Atletas com onboarding CONCLUÍDO — a lista que TODO job de fundo
        (plano de domingo, briefing, pollers, proativos, informativos) percorre.
        O cadastro pelo app cria um perfil-esqueleto (`onboarding_complete=False`,
        idade 0, sem objetivo) antes do wizard; ele não pode receber plano nem
        mensagem. Perfis antigos não têm o campo e contam como concluídos.
        `list_all` fica só pra unicidade de slug/cadastro e debug."""

        return [
            profile
            for profile, runner in self._valid_profiles()
            if getattr(runner, "onboarding_complete", True)
        ]

    def _valid_profiles(
        self,
    ):

        for file in self.storage.glob("*.json"):

            profile = file.stem

            try:

                runner = self.load(profile)

            except Exception:

                continue

            yield profile, runner