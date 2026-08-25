"""Cardápio de estímulos de corrida — a EXPERTISE de periodização compartilhada
entre o plano da semana (CoachPlanEngine) e o treino AVULSO (OneOffWorkoutEngine).
Fonte ÚNICA: os dois montam treino do mesmo leque, sem um saber menos que o outro
(o avulso servia o treinador externo com estímulo genérico — este catálogo fecha
o gap). Ver [[project_treino_avulso]] e [[project_renato_perfil_real]]."""

# o LEQUE de tipos (o catálogo fisiológico) — cada um com o estímulo que traz.
# Sem chaves `{}`: entra cru num .format() de prompt.
WORKOUT_MENU = """\
    * Intervalado curto (VO2): 200-800m fortes + recuperação (ex.: 8x400,
      5x800) — potência aeróbica.
    * Intervalado longo / cruzeiro: 1000-2000m perto do limiar (ex.: 4x1000,
      3x1600) — resistência à velocidade.
    * Tempo / Limiar contínuo: 20-40 min "confortavelmente difícil" (ritmo de
      limiar) — o motor pra 10k/21k.
    * Fartlek: variações livres de ritmo (ex.: 2min forte / 2min leve x6-8, ou
      por sensação) — troca de ritmo, quebra a monotonia.
    * Progressivo: começa fácil e ACELERA em blocos até forte no fim — ensina a
      terminar forte (ótimo no longão).
    * Longão: o treino mais longo — constante, progressivo OU com blocos no
      ritmo-alvo (varie a forma dele também).
    * Simulado / prova-teste: o ENSAIO GERAL da prova — um bloco CONTÍNUO no
      RITMO-ALVO cobrindo um pedação grande da distância (NÃO a prova inteira),
      pra o atleta testar se SUSTENTA o pace e treinar o pacing/confiança
      ("seguro ou quebro?"). É DIFERENTE do tiro: o tiro constrói a capacidade
      em pedaços; o simulado testa MANTER contínuo. Ex.: pré-10k -> ~6-8 km no
      pace-alvo; pré-21k -> ~12-16 km com um bloco grande no alvo; pré-5k ->
      ~3-4 km no alvo. Aquece antes, solta depois.
    * Regenerativo/base: rodagem leve pra absorver a carga."""

# a periodização em uma frase: qual ênfase puxar conforme a distância pra prova
PHASE_EMPHASIS = (
    "longe da prova / construindo base -> volume, longão, tempo de limiar; "
    "perto da prova -> afinar no ritmo-alvo (tiros no pace de prova) E encaixar "
    "UM simulado/prova-teste contínuo no ritmo-alvo como ensaio geral "
    "(~10-14 dias antes num 5k/10k, ~2-3 semanas numa meia/maratona), com dias "
    "leves em volta pra chegar recuperado; véspera -> poupar"
)

# POR TEMPO vs POR DISTÂNCIA — compartilhada pelos 3 motores (plano semanal,
# negociação, avulso). Sem chaves `{}`: entra crua num .format() de prompt.
# Bug real (03/08): atleta pediu "50 min de rodagem" e o coach converteu em
# "8 km". Tempo NÃO é só reativo — é uma forma de prescrição de primeira classe
# que o treinador pode PROPOR sozinho (ex.: longão por tempo em pé, "1h45 de
# rodagem"), pra TODOS os atletas. Ver [[project_tudo_dinamico]].
TIME_OR_DISTANCE_RULE = (
    "POR TEMPO OU POR DISTÂNCIA — as duas são formas VÁLIDAS de prescrever e "
    "VOCÊ (treinador) escolhe a que servir melhor a cada sessão. Distância "
    "(distance_km) é o padrão comum. Mas TEMPO (minutos) é uma opção de "
    "PRIMEIRA CLASSE que você pode PROPOR por conta própria — natural pra "
    "rodagem/base e principalmente pro LONGÃO (tempo em pé; ex.: \"1h de "
    "rodagem leve\", \"longão de 1h45\"). E SEMPRE que o atleta PEDIR ou "
    "PREFERIR por tempo (pedido na mensagem ou preferência na memória), "
    "prescreva em minutos. Sessão por tempo: use \"duration_min\" no lugar de "
    "\"distance_km\" (fica SEM km) e monte os \"steps\" por tempo "
    "(\"duration_min\"). NUNCA converta em km os minutos que ele pediu."
)
