"""Ausência que o atleta DECLAROU e ainda não acabou (viagem, afastamento médico,
repouso). É o que os proativos consultam pra não tratar quem AVISOU que ia parar
como quem simplesmente sumiu — o mesmo papel do [[IllnessEpisode]] pra doença,
mas vindo da memória do coach: o prazo é o `expires_at` do fato (escrito pela
extração a partir da mensagem; a rede do [[MemoryLifecycle]] deduz "por 7 dias"
quando a IA deixa escapar).

Fonte única: quem precisar saber "ele está em pausa combinada?" pergunta aqui,
em vez de cada notificador ler texto de memória por conta própria."""

from dataclasses import dataclass
from datetime import date

from app.domain.memory_lifecycle import MemoryLifecycle
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)


@dataclass(frozen=True, slots=True)
class AbsenceWindow:

    # último dia da ausência (o atleta volta no dia seguinte)
    until: date

    # o fato como o coach o anotou (com as datas)
    note: str

    @staticmethod
    def open(profile: str, today: date) -> "AbsenceWindow | None":
        """A ausência declarada que segue valendo em `today`, ou None. Se houver
        mais de uma, vale a que termina por último. Best-effort: memória
        ilegível não derruba o proativo (segue como se não houvesse ausência)."""

        try:

            entries = RunnerMemoryRepository().active(profile)

        except Exception as e:  # noqa: BLE001

            print(f"Ausência declarada indisponível p/ '{profile}': {e}")

            return None

        best: AbsenceWindow | None = None

        for entry in entries:

            if not MemoryLifecycle.is_absence(entry.category, entry.content):

                continue

            expiry = entry.expires_at or MemoryLifecycle.expiry_for(
                entry.category, entry.content, entry.created_at,
            )

            if not expiry:

                continue

            try:

                until = date.fromisoformat(expiry[:10])

            except ValueError:

                continue

            if until < today:

                continue

            if best is None or until > best.until:

                best = AbsenceWindow(until=until, note=entry.content)

        return best
