"""Descoberta (discoverability): o bot entende vários pedidos em linguagem
natural (ver [[IntentRouter]]), mas o atleta não tem como adivinhar quais. Duas
peças resolvem isso:

- `card(name)`: o CARDÁPIO completo do que dá pra perguntar — resposta ao
  "ajuda / o que você faz / menu". Referência sempre-disponível, só aparece
  quando pedem (nunca incomoda).
- `weekly_tip(week_index)`: uma dica "💡 Você sabia?" por vez, rotacionando —
  vai no rodapé do resumo de domingo pra quem já passou do onboarding descobrir
  aos poucos, sem spam.

Determinístico e puro (texto fixo, sem IA). Ver [[project_ideias_produto]]."""


class HelpMenu:

    @staticmethod
    def card(runner_name: str) -> str:
        """O cardápio de perguntas — o que o atleta pode pedir ao bot."""

        return "\n".join(
            [
                f"🤖 O que você pode me perguntar, {runner_name}:",
                "",
                "🏃 Treino",
                '• "Qual meu treino de hoje?" ou "próximo treino?"',
                '• "Qual meu plano da semana?"',
                '• "Como foi meu último treino?"',
                '• "Monta um treino pra domingo" — pra um dia que faltou '
                "no seu plano",
                "",
                "💪 Seu corpo e sua forma",
                '• "Como está meu corpo?" — recuperação e carga',
                '• "Estou evoluindo?" — sua forma ao longo das semanas',
                '• "Como estou?" — o retrato completo (corpo + forma)',
                "",
                "💬 E pode falar comigo normal",
                "Me conta como se sente (\"dormi mal\", \"perna doendo\"), "
                "peça pra trocar seu objetivo, ou negocie um treino que não "
                "curtiu — eu me viro no meio da conversa. 👊",
            ]
        )

    # dicas rotativas: uma por semana, cobrindo os pedidos mais úteis. A ordem
    # importa pouco (rotaciona), mas as mais valiosas vêm primeiro.
    _TIPS = [
        '💡 Você sabia? É só me perguntar "como estou?" que eu te mando um '
        "retrato completo — corpo e forma juntos.",
        '💡 Você sabia? Pergunte "estou evoluindo?" quando quiser ver se sua '
        "forma vem subindo ao longo das semanas.",
        '💡 Você sabia? "Como está meu corpo?" te mostra recuperação e carga '
        "do jeito honesto, sem susto.",
        '💡 Você sabia? "Qual meu próximo treino?" te dá a sessão detalhada na '
        "hora, a qualquer momento.",
        "💡 Você sabia? Pode me contar como se sente — \"dormi mal\", \"perna "
        'doendo" — que eu levo em conta na sua dose.',
        '💡 Você sabia? "Qual meu plano da semana?" te mostra a agenda inteira, '
        "com o que já foi feito marcado.",
        '💡 Você sabia? Mande "ajuda" a qualquer hora pra ver tudo que dá pra '
        "me perguntar.",
        '💡 Você sabia? Se faltar treino num dia (o seu ou do seu treinador), '
        'peça "monta um treino pra domingo" que eu crio um pros seus dados.',
    ]

    @staticmethod
    def weekly_tip(week_index: int) -> str:
        """Uma dica '💡 Você sabia?' pro rodapé do resumo, rotacionando pelo
        número da semana — diferente a cada domingo, cobre o ciclo em ~7 semanas
        antes de repetir."""

        return HelpMenu._TIPS[week_index % len(HelpMenu._TIPS)]
