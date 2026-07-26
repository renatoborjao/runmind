import re
import unicodedata
from enum import Enum


class ChatIntent(str, Enum):
    """Perguntas que têm resposta canônica e completa no sistema —
    respondê-las de forma determinística evita que o Gemini resuma ou
    reformate (e desconfigure) dados que já temos prontos."""

    LAST_TRAINING = "LAST_TRAINING"

    NEXT_TRAINING = "NEXT_TRAINING"

    WEEKLY_PLAN = "WEEKLY_PLAN"

    BODY_READING = "BODY_READING"

    FITNESS_TREND = "FITNESS_TREND"

    STATE_PORTRAIT = "STATE_PORTRAIT"

    HELP = "HELP"


# Pedido claro sobre o treino JÁ FEITO (quer a análise completa).
_LAST_PATTERNS = [
    r"como (foi|ficou|fiquei|fui|foi que foi)\b.*\b(treino|corrida|rodagem|correr|corri|longao)",
    r"\b(ultimo treino|ultima corrida|treino passado|treino de ontem)\b.*\b(como|analise|resultado|resumo|mostra|ver|detalh)",
    r"\b(analise|resultado|resumo|feedback|balanco)\b.*\b(treino|corrida|rodagem)",
    r"\b(me mostra|mostra|ver|quero ver)\b.*\b(ultimo|ultima)\b.*\b(treino|corrida)",
    r"como que (foi|ficou)\b.*\b(treino|corrida)",
]

# Pedido claro sobre o PRÓXIMO treino (quer a sessão detalhada).
_NEXT_PATTERNS = [
    r"\b(proximo treino|proxima corrida|proximo treinamento|proxima sessao)\b",
    r"\bquando\b.*\b(treino|treinar|corrida|correr|rodar|proxima)\b",
    r"\bqual\b.*\b(proximo|proxima)\b.*\b(treino|corrida)",
    r"\b(treino|corrida) (de|pra|para) (amanha|hoje)\b",
    r"\bqual\b.*\b(meu|o)\b.*\b(treino|corrida)\b.*\b(agora|hoje|amanha|proximo)\b",
    r"\b(o que|oq|o q)\b.*\b(treino|faco|corro|rodo|devo fazer)\b.*\b(hoje|amanha|agora)\b",
]

# Pedido do plano da semana inteiro (quer a agenda, não uma sessão só).
_WEEKLY_PLAN_PATTERNS = [
    r"\bplano\b.*\b(semana|treino|treinos|corrida)\b",
    r"\b(qual|meu|meus|quais|ver|mostra|manda|me manda)\b.*\bplano\b",
    r"\btreinos da semana\b",
    r"\bagenda (da|de) (semana|treino)\b",
]

# Pedido sobre o CORPO/recuperação (quer a leitura carga+recuperação).
_BODY_PATTERNS = [
    r"\bcomo (esta|ta|to|estou|tou)\b.*\b(meu corpo|minha recuperacao|recuperado|descansado|de recuperacao|minha fadiga|meu descanso)\b",
    r"\b(minha|meu) (recuperacao|prontidao|sobrecarga|fadiga)\b",
    r"\b(estou|to|tou|ando)\b.*\b(sobrecarregado|cansado|recuperado|descansado|detonado|zerado)\b",
    r"\bposso (treinar|puxar|forcar|correr)\b.*\b(forte|pesado|firme)\b",
    r"\bcomo (esta|ta)\b.*\b(meu sono|meu hrv|minha vfc|minha carga)\b",
    r"\bleitura do (meu )?corpo\b",
    r"\b(meu sono|meu hrv|minha vfc|minha frequencia (cardiaca )?de repouso|meu body battery|minha bateria corporal)\b",
]

# Pergunta sobre EVOLUÇÃO/forma ("estou melhorando?") — quer a leitura de
# eficiência aeróbica ao longo do tempo, eixo diferente da recuperação/corpo.
_FITNESS_PATTERNS = [
    r"\b(estou|to|tou|ando)\b.*\b(evoluindo|melhorando|progredindo|mais rapido|mais veloz|mais em forma|mais forte)\b",
    r"\b(minha|meu)\b.*\b(evolucao|progresso|forma fisica|eficiencia|condicionamento|fitness)\b",
    r"\b(estou|to|tou)\b.*\bem forma\b",
    r"\b(melhorei|evolui|progredi)\b",
    r"\bficando (mais )?em forma\b",
    r"\b(estou|to) ficando (melhor|mais rapido|mais veloz)\b",
    r"\bmeu (fitness|condicionamento|fisico)\b",
]

# Pergunta HOLÍSTICA ("como estou no geral / me dá um raio-x") — quer o retrato
# unificado (corpo & carga + forma), não um eixo só. Frases genéricas de
# propósito, distintas de corpo/forma (que exigem palavra específica).
_PORTRAIT_PATTERNS = [
    r"^como (eu )?(estou|to|tou|ando)\s*\??$",
    r"\bcomo (eu )?(estou|to|tou|ando) (no geral|de modo geral|no momento|indo|hoje)\b",
    r"\bpanorama\b",
    r"\braio.?x\b",
    r"\b(visao|resumo|quadro|estado) geral\b",
    r"\bcomo (voce )?me ve\b",
    r"\bmeu (estado|panorama)\b",
    r"\bme (da|de|manda|mostra) (um |o )?(raio.?x|panorama|resumo geral|quadro geral)\b",
]

# Pedido de AJUDA/descoberta ("o que dá pra te perguntar?") — quer o cardápio
# do que o bot responde. Cobre "/ajuda", "menu", "o que você faz".
_HELP_PATTERNS = [
    r"^/?ajuda\b",
    r"^/?help\b",
    r"^/?menu\b",
    r"^/?comandos?\b",
    r"\bo que (voce|vc|tu) (faz|sabe fazer|pode fazer|consegue fazer)\b",
    r"\bo que (eu )?(posso|da pra|consigo) (perguntar|pedir|te perguntar)\b",
    r"\bcomo (voce|vc) funciona\b",
    r"\bquais (perguntas|comandos|opcoes)\b",
    r"\bpra que (voce|vc) serve\b",
]

_LAST_REGEXES = [re.compile(p) for p in _LAST_PATTERNS]

_NEXT_REGEXES = [re.compile(p) for p in _NEXT_PATTERNS]

_WEEKLY_PLAN_REGEXES = [re.compile(p) for p in _WEEKLY_PLAN_PATTERNS]

_BODY_REGEXES = [re.compile(p) for p in _BODY_PATTERNS]

_FITNESS_REGEXES = [re.compile(p) for p in _FITNESS_PATTERNS]

_PORTRAIT_REGEXES = [re.compile(p) for p in _PORTRAIT_PATTERNS]

_HELP_REGEXES = [re.compile(p) for p in _HELP_PATTERNS]


class IntentRouter:

    @staticmethod
    def detect(text: str) -> ChatIntent | None:
        """Só devolve uma intenção quando o pedido é inequívoco. Se a
        mensagem casa com mais de uma (ou nenhuma), devolve None e a
        conversa segue para o Gemini — evita mostrar o card errado."""

        normalized = IntentRouter._normalize(text)

        matched = []

        if any(regex.search(normalized) for regex in _LAST_REGEXES):

            matched.append(ChatIntent.LAST_TRAINING)

        if any(regex.search(normalized) for regex in _NEXT_REGEXES):

            matched.append(ChatIntent.NEXT_TRAINING)

        if any(regex.search(normalized) for regex in _WEEKLY_PLAN_REGEXES):

            matched.append(ChatIntent.WEEKLY_PLAN)

        if any(regex.search(normalized) for regex in _BODY_REGEXES):

            matched.append(ChatIntent.BODY_READING)

        if any(regex.search(normalized) for regex in _FITNESS_REGEXES):

            matched.append(ChatIntent.FITNESS_TREND)

        if any(regex.search(normalized) for regex in _PORTRAIT_REGEXES):

            matched.append(ChatIntent.STATE_PORTRAIT)

        if any(regex.search(normalized) for regex in _HELP_REGEXES):

            matched.append(ChatIntent.HELP)

        if len(matched) == 1:

            return matched[0]

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        """Minúsculas, sem acento e com espaços colapsados — as regras
        ficam livres de acento ('proximo' cobre 'próximo')."""

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
