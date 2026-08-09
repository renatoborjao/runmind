from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.workout_step import WorkoutStep


@dataclass(slots=True)
class PlannedSession:

    day: str

    workout_type: str

    objective: str

    planned_distance_km: float | None

    planned_duration_minutes: int | None

    target_pace_min: str | None

    target_pace_max: str | None

    notes: str = ""

    adjusted: bool = False

    adjustment_reason: str | None = None

    # km ESTIMADO de uma sessão por tempo (duração ÷ pace), preenchido na
    # geração do plano — pra o volume contar TODOS os tipos, não só os por
    # distância (treino "45 min" deixava de somar km). None quando é por
    # distância (usa planned_distance_km) ou quando não dá pra estimar.
    estimated_distance_km: float | None = None

    # km REAL executado nesta sessão (do treino que casou no histórico) —
    # preenchido na leitura, pra o "✅ feito" mostrar "45 min → 6,2 km" em
    # QUALQUER tipo. None = ainda não feito / sem treino casado.
    executed_distance_km: float | None = None

    # Estrutura de intervalos para run/walk (caminhada/trote). Quando
    # presente, a sessão é medida em tempo, não em km. Ex:
    #   {"warmup_min": 5, "trot_sec": 60, "walk_sec": 180,
    #    "reps": 6, "cooldown_min": 5}
    intervals: dict | None = None

    # Modalidade da sessão: "run" (corrida), "walk" (caminhada) ou
    # "run_walk" (corrida-caminhada, iniciante). O plano é SÓ de
    # corrida/caminhada — musculação e outras atividades não entram.
    kind: str = "run"

    # Origem da sessão: "plan" (parte do plano da semana — nosso ou do
    # treinador externo) ou "oneoff" (treino AVULSO que montamos sob demanda
    # pra um dia específico que o plano não cobria). O avulso é empurrado ao
    # relógio isolado do resto e reconhecido como nosso na avaliação pós-treino.
    origin: str = "plan"

    # Riqueza do plano gerado pela IA-treinadora: como executar (blocos,
    # séries, strides, fechamento progressivo) e o porquê do treino.
    structure: str = ""

    purpose: str = ""

    # Passos ESTRUTURADOS do treino (aquecimento, séries, recuperação,
    # desaquecimento...) — fonte de verdade pra montar o treino guiado no
    # Garmin. Vazio = cai no fallback (distância+pace num passo só).
    steps: list[WorkoutStep] = field(default_factory=list)

    # Registro do que ESTA sessão colocou no Garmin do atleta — pra
    # reconciliar mudanças no meio da semana sem duplicar nem deixar
    # treino-fantasma no relógio. None = nunca empurrada. Chaves:
    #   workout_id, schedule_id, date (ISO) e fingerprint (hash do
    #   conteúdo empurrado: se o treino muda, o fingerprint muda e a
    #   reconciliação desagenda o antigo e empurra o novo).
    garmin: dict | None = None

    @property
    def effective_distance_km(self) -> float | None:
        """km da sessão pra CONTABILIDADE de volume — vale pra TODOS os tipos:
        a distância planejada quando há; senão a estimativa (duração ÷ pace)
        guardada pra sessão por tempo. None só quando não dá pra saber."""

        if self.planned_distance_km:

            return self.planned_distance_km

        return self.estimated_distance_km