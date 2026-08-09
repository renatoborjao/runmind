"""Brief de LONGO PRAZO do atleta — fonte ÚNICA do "quem é esse atleta".

Reúne evolução da forma + memória evolutiva (o que ele contou) + aprendizados do
coach num bloco pronto pra injetar em QUALQUER superfície que fala/decide (chat,
análise, mensagens proativas). É a materialização da LEI
[[feedback_base_historico_sempre]]: nenhuma resposta genérica — sempre com o
histórico de quem é o atleta. Best-effort: cada peça que falhar não entra; nunca
levanta exceção (o chamador segue com o que tiver, ou vazio).

Antes isto vivia duplicado dentro do AIAnalysisWriter; centralizar aqui evita
divergência e faz "ligar em mais uma superfície" custar uma linha."""


class AthleteLongTermBrief:

    _DEFAULT_HEADER = (
        "QUEM É O ATLETA NO LONGO PRAZO (memória, aprendizados e evolução — "
        "considere SEMPRE; fale com FATO, nunca genérico):"
    )

    @staticmethod
    def render(profile: str, header: str | None = None) -> str:
        """Bloco com evolução + memória + aprendizados (ou "" se não há lastro
        de nada). `header` permite ao chamador ajustar o enquadramento."""

        lines = AthleteLongTermBrief._lines(profile)

        if not lines:

            return ""

        return (header or AthleteLongTermBrief._DEFAULT_HEADER) + "\n" + "\n".join(lines)

    @staticmethod
    def _lines(profile: str) -> list[str]:

        lines: list[str] = []

        try:

            from app.application.coach.intelligence.fitness_reading_service import (  # noqa: E501
                FitnessReadingService,
            )
            from app.application.coach.writer.fitness_evolution_writer import (
                FitnessEvolutionWriter,
            )

            evo = FitnessEvolutionWriter.line(
                FitnessReadingService.read_evolution(profile)
            )

            if evo:

                lines.append(f"Evolução da forma: {evo}")

        except Exception as e:

            print(f"Brief (evolução) falhou p/ '{profile}': {e}")

        try:

            from app.application.coach.memory.runner_memory_service import (
                RunnerMemoryService,
            )

            memory = RunnerMemoryService.render(profile)

            if memory:

                lines.append(memory)

        except Exception as e:

            print(f"Brief (memória) falhou p/ '{profile}': {e}")

        try:

            from app.core.config import get_settings

            if get_settings().coach_learning_inject_enabled:

                from app.application.coach.memory.coach_learning_service import (
                    CoachLearningService,
                )

                learnings = CoachLearningService.render(profile)

                if learnings:

                    lines.append(learnings)

        except Exception as e:

            print(f"Brief (aprendizados) falhou p/ '{profile}': {e}")

        return lines
