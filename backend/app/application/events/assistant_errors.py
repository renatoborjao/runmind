class AssistantUnavailable(RuntimeError):
    """A IA conversacional (Gemini) não conseguiu responder AGORA, mesmo
    depois da cascata de modelos + backoff. É um SINAL pro webhook adiar e
    tentar de novo (a janela de rate limit reseta) em vez de já jogar o
    "me embananei" na cara do atleta — assim ele recebe a resposta de
    verdade, só um pouco depois.

    Vale tanto pra conversa do coach quanto pro onboarding. Só é levantada
    quando ainda há fôlego de retry (send_fallback=False) e num ponto ANTES
    de qualquer efeito colateral (envio/gravação de estado), pra o
    reprocessamento ser idempotente.
    """
