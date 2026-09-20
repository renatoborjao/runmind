"""Limpa a mensagem de feedback pós-treino pra virar a ANÁLISE mostrada na tela
da atividade no app. Tira o que não é "análise daquele treino":

- a seção "🎯 Próximo treino" (o próximo treino tem lugar próprio no app —
  home e aba Treino; na análise da corrida só polui);
- as caudas de chat: a pergunta de RPE (💬) e a nota de tênis (👟), que só
  fazem sentido na conversa, não numa tela de leitura.

Mantém o corpo da análise (📅 Planejado, ✅ Executado, 🧩 blocos, ⏱️ parciais,
📊 Análise, 📈 Histórico, ❤️ Recuperação) e o fechamento (➡️), que é orientação
do próximo passo/recuperação, não os DADOS do próximo treino.

Fonte única, usada pelo evento (treinos novos) e pelo backfill (retroativo)."""

from app.core import messages

# caudas de chat que vêm DEPOIS da análise (cada uma precedida de linha em branco)
_TAIL_MARKERS = ("\n\n💬", "\n\n👟")


class AnalysisCleaner:

    @staticmethod
    def clean(text: str) -> str:
        """Análise pronta pra tela: sem próximo treino e sem caudas de chat."""

        return AnalysisCleaner._strip_next_training(
            AnalysisCleaner._strip_tails(text)
        ).strip()

    @staticmethod
    def _strip_tails(text: str) -> str:
        """Corta a partir da 1ª cauda de chat (RPE/tênis)."""

        cut = len(text)

        for marker in _TAIL_MARKERS:

            i = text.find(marker)

            if i != -1:

                cut = min(cut, i)

        return text[:cut]

    @staticmethod
    def _strip_next_training(text: str) -> str:
        """Remove a seção '🎯 Próximo treino' (título + bullets), preservando a
        linha em branco de separação e o que vem depois (ex.: fechamento ➡️)."""

        out: list[str] = []

        skipping = False

        for line in text.split("\n"):

            stripped = line.strip()

            if stripped == messages.NEXT_TRAINING_TITLE:

                skipping = True

                continue

            if skipping:

                # bullets da seção → descarta
                if stripped.startswith("•"):

                    continue

                # fim da seção
                skipping = False

                # a linha em branco que fechava a seção é descartada (a de cima,
                # que separava da recuperação, fica como separador)
                if stripped == "":

                    continue

            out.append(line)

        return "\n".join(out)
