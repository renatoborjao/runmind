from app.application.coach.analysis_cleaner import AnalysisCleaner

_FULL = """🏃 Ritmind

Parabéns pelo treino, Renato! 👊

📅 Planejado
• sábado (19/09)
• Rodagem
• 8.0 km

✅ Executado
• Distância: 8.1 km

📊 Análise
• Rodagem sólida.

❤️ Recuperação
• Durma bem.

🎯 Próximo treino
• quarta (23/09)
• Intervalado · 6 km

➡️ Bora que a semana tá indo bem.

💬 De 0 a 10, quão puxado foi? (só o número)

👟 Contei essa no teu Boston — se foi outro, me fala."""


def test_remove_proximo_treino_e_caudas():

    out = AnalysisCleaner.clean(_FULL)

    assert "🎯 Próximo treino" not in out
    assert "quarta (23/09)" not in out
    assert "Intervalado · 6 km" not in out
    # caudas de chat fora
    assert "De 0 a 10" not in out
    assert "Contei essa" not in out
    # corpo e fechamento preservados
    assert "📅 Planejado" in out
    assert "📊 Análise" in out
    assert "❤️ Recuperação" in out
    assert "➡️ Bora que a semana tá indo bem." in out
    # separação preservada entre recuperação e fechamento (sem colar)
    assert "• Durma bem.\n\n➡️" in out


def test_sem_proximo_treino_nao_altera_corpo():
    """Semana concluída: não há seção de próximo treino — corpo intacto."""

    txt = "📊 Análise\n• Boa.\n\n❤️ Recuperação\n• Descansa.\n\n➡️ Fecha a semana."

    out = AnalysisCleaner.clean(txt)

    assert out == txt


def test_proximo_treino_no_fim_sem_fechamento():

    txt = ("📊 Análise\n• Boa.\n\n🎯 Próximo treino\n• quinta (24/09)\n• Longão")

    out = AnalysisCleaner.clean(txt)

    assert out == "📊 Análise\n• Boa."
