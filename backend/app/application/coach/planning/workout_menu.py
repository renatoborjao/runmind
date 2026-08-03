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
    * Regenerativo/base: rodagem leve pra absorver a carga."""

# a periodização em uma frase: qual ênfase puxar conforme a distância pra prova
PHASE_EMPHASIS = (
    "longe da prova / construindo base -> volume, longão, tempo de limiar; "
    "perto da prova -> afinar no ritmo-alvo (tiros no pace de prova); "
    "véspera -> poupar"
)

# POR TEMPO vs POR DISTÂNCIA — compartilhada pelos 3 motores (plano semanal,
# negociação, avulso). Sem chaves `{}`: entra crua num .format() de prompt.
# Bug real (03/08): atleta pediu "50 min de rodagem" e o coach converteu em
# "8 km"; ele já preferia por tempo. Ver [[project_tudo_dinamico]].
TIME_OR_DISTANCE_RULE = (
    "POR TEMPO OU POR DISTÂNCIA: por padrão prescreva em distância "
    '(distance_km). MAS se o atleta PEDIR ou PREFERIR treinar por TEMPO (ex.: '
    '"quero 50 min de rodagem", ou a memória/preferência dele diz que prefere '
    'por minutos), prescreva a sessão em MINUTOS: use "duration_min" no lugar '
    'de "distance_km" (a sessão fica SEM km) e monte os "steps" por tempo '
    '("duration_min"). NUNCA converta os minutos que ele pediu em km — respeite '
    "a unidade que ele quer."
)
