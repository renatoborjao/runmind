"""Cardápio de estímulos de corrida — a EXPERTISE de periodização compartilhada
entre o plano da semana (CoachPlanEngine) e o treino AVULSO (OneOffWorkoutEngine).
Fonte ÚNICA: os dois montam treino do mesmo leque, sem um saber menos que o outro
(o avulso servia o treinador externo com estímulo genérico — este catálogo fecha
o gap). Ver [[project_treino_avulso]] e [[project_renato_perfil_real]]."""

# o LEQUE de tipos (o catálogo fisiológico) — cada um com o estímulo que traz.
# Sem chaves `{}`: entra cru num .format() de prompt.
WORKOUT_MENU = """\
  BASE / AERÓBICO
    * Regenerativo: bem leve e curto, pra absorver carga (pode virar trote +
      caminhada).
    * Rodagem leve (Z2): contínua e conversável — por pace OU por FC (bom pra
      quem está com recuperação em queda ou no calor).
    * Rodagem moderada / steady: contínua um degrau acima do leve (perto do
      ritmo de maratona) — resistência aeróbica sem virar treino forte.
    * Rodagem com acelerações (strides): rodagem leve + 4-8 acelerações de
      15-20 s soltas no fim (recupera andando/trotando) — economia e técnica
      sem custo de recuperação.
    * Longão: o treino mais longo — constante, por TEMPO em pé, com FINAL
      RÁPIDO (últimos 2-3 km mais fortes) OU com blocos no ritmo-alvo (varie a
      forma dele também).
  LIMIAR
    * Tempo / Limiar contínuo: 20-40 min "confortavelmente difícil" — o motor
      pra 10k/21k.
    * Limiar intervalado / cruzeiro: 1000-2000m no limiar com pausa curta (ex.:
      4x1600, 3x2000) — mais volume de limiar com menos custo.
    * Alternado / over-under: blocos oscilando um pouco acima e abaixo do
      limiar (ex.: 4x(3min acima + 2min abaixo)) — ensina a limpar lactato em
      movimento.
    * Progressivo: começa fácil e ACELERA em blocos até forte no fim — ensina a
      terminar forte.
    * Tempo com surges: tempo contínuo com acelerações curtas no meio (ex.:
      30 s mais forte a cada 5 min) — simula ataque/mudança de ritmo em prova.
  VELOCIDADE / VO2
    * Intervalado curto (VO2): 200-800m fortes + recuperação (ex.: 8x400,
      5x800) — potência aeróbica.
    * Intervalado longo (VO2): 1000-1200m no ritmo de 5k (ex.: 5x1000) —
      VO2 sustentado.
    * Pirâmide / escada: distâncias que sobem e descem (ex.: 200-400-600-800-
      600-400-200) — varia o estímulo e a cabeça.
    * Tiros curtos de velocidade: 100-200m rápidos com recuperação COMPLETA —
      neuromuscular/economia (não é pra cansar).
    * Fartlek: variações de ritmo livres ou estruturadas (ex.: 2min forte /
      2min leve x6-8, ou por poste/sensação; Mona fartlek 90s-60s-30s-15s) —
      troca de ritmo, quebra a monotonia.
    * Cutdown / negativo: cada repetição um pouco MAIS RÁPIDA que a anterior
      (ex.: 4x1600 do limiar ao pace de 5k) — ensina a acelerar cansado.
    * Recuperação rodando (float): intervalos em que a pausa é trote
      MODERADO, não parado (ex.: 8x400 com 200 float) — mais aeróbico,
      específico pra 10k/21k.
  RITMO DE PROVA
    * Blocos no pace-alvo: repetições longas no ritmo da prova (ex.: 3x3km no
      pace de 21k, 5x1km no pace de 10k; Yasso 800 pra maratona) — acostuma o
      corpo ao ritmo.
    * Michigan / sessão mista: numa sessão só, blocos de distâncias e ritmos
      diferentes (ex.: 1600 limiar + 1200 + 800 + 400 cada vez mais forte,
      com trechos de tempo entre eles) — específico e desafiador, pra fase de
      pico.
    * Simulado / prova-teste: o ENSAIO GERAL da prova — um bloco CONTÍNUO no
      RITMO-ALVO cobrindo um pedação grande da distância (NÃO a prova inteira),
      pra o atleta testar se SUSTENTA o pace e treinar o pacing/confiança
      ("seguro ou quebro?"). É DIFERENTE do tiro: o tiro constrói a capacidade
      em pedaços; o simulado testa MANTER contínuo. Ex.: pré-10k -> ~6-8 km no
      pace-alvo; pré-21k -> ~12-16 km com um bloco grande no alvo; pré-5k ->
      ~3-4 km no alvo. Aquece antes, solta depois.
    * Teste / contrarrelógio: 3k-5k no máximo sustentável (ou 30 min) pra
      MEDIR a evolução e recalibrar paces/zonas — raro, com o corpo descansado.
  INICIANTE / RETORNO
    * Caminhada ativa: caminhada em ritmo firme por tempo — base pra quem
      está começando ou voltando.
    * Corrida-caminhada (run-walk): alterna trote e caminhada (ex.: 8x(1min
      trote + 2min caminhada)), progredindo a parte corrida semana a semana.
    * Retorno de pausa/lesão: rodagem curta por tempo e FC baixa, sem
      intensidade, subindo aos poucos.
  TÉCNICA
    * Educativos (skipping, anfersen, dribling) no aquecimento antes de um
      treino de qualidade — em passo aberto (sem alvo).
    * Cadência: rodagem leve com trechos focados em passada curta e rápida
      (ex.: 6x1min pensando em cadência alta) — economia e menos impacto.
  O cardápio é o PONTO DE PARTIDA, não uma caixa fechada: qualquer estrutura
  que um treinador de verdade prescreveria é válida — e se o atleta PEDIR um
  tipo (mesmo fora da lista), monte-o. Treino de SUBIDA/rampa não entra no
  plano da semana: é particular do percurso de cada um, só quando ele pede."""

# SUBIDA fica FORA do plano da semana (Renato 27/09: "é algo muito particular,
# tem que ser pedido meio que avulso") — só o treino AVULSO a oferece.
HILL_MENU = """  FORÇA ESPECÍFICA
    * Subida / tiros em rampa: 6-12x 30-90 s subindo forte, desce trotando —
      força, potência e economia (alvo por ESFORÇO/FC, não pace; fim por
      tempo ou no botão).
    * Circuito de subida (Kenyan hills): sobe E desce num circuito contínuo
      em esforço moderado-forte por 15-30 min — força + aeróbico juntos.
    * Descida controlada: tiros curtos em descida suave, passada solta —
      prepara o quadríceps pra prova com descida e melhora a cadência.
    * Terreno ondulado / trilha: rodagem ou longão em sobe-desce, por tempo e
      FC (pace não vale em subida)."""

ONE_OFF_MENU = WORKOUT_MENU + "\n" + HILL_MENU

# como descrever os passos ESTRUTURADOS (viram treino guiado no relógio) —
# fonte única pros motores que montam sessão. Sem chaves duplas: entra como
# VALOR num .format() (o valor não é reprocessado).
STEPS_RULE = """\
"steps" é a MESMA prescrição em formato ESTRUTURADO (vira treino guiado no \
relógio). Use os blocos reais do treino, na ordem:
    * kind: "warmup" | "run" | "interval" | "recovery" | "rest" | "cooldown" \
| "repeat"
    * fim do bloco: "distance_m" OU "distance_km" OU "duration_min" — ou NENHUM \
(bloco ABERTO: avança quando o atleta aperta a volta; bom pra educativos, \
subida "até o topo", recuperação por sensação)
    * alvo: "pace_min"/"pace_max" (mm:ss por km; min = mais rápido) OU \
"hr_min"/"hr_max" (bpm — use em subida, trilha, calor, rodagem por FC); \
recuperação/aquecimento podem ir sem alvo
    * "repeat" agrupa o que se repete: {"kind":"repeat","reps":6,"steps":[bloco \
de esforço, bloco de recuperação]} (repeat dentro de repeat vale pra séries)
  O formato aceita QUALQUER treino: contínuo, intervalado, pirâmide, subida, \
run-walk, strides, fartlek, progressivo, blocos no pace de prova.
  Cada passo é uma MUDANÇA REAL de estímulo — no relógio, cada passo apita e \
troca de tela como um bloco novo. Trecho CONTÍNUO no mesmo alvo = UM passo só \
(rodagem de 8 km = 1 passo de 8 km; progressivo = um passo por trecho de \
ritmo). Nunca fatie um contínuo em passos de 1 km: o atleta sente cada km \
como um bloco novo (vira um intervalado falso) e o relógio já marca cada km \
sozinho (volta automática). Parcial por km (estratégia de prova) vai no \
texto, não nos passos."""

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
