"""A SÍNTESE cruzada do retrato "como você está" — o valor que só a UNIÃO dos
eixos entrega, e que três leituras avulsas nunca dão.

Corpo (aguenta? = carga à luz da recuperação) e Forma (evolui? = economia
aeróbica ao longo das semanas) são eixos IRMÃOS. Sozinho, cada um responde uma
pergunta; cruzados, respondem a que importa: *o que fazer agora*. Ex.: forma
subindo + corpo absorvendo = janela pra progredir; forma subindo + corpo
pedindo freio = segura a mão pra não trocar ganho por fadiga.

Puro/determinístico: recebe os vereditos já prontos (BodyReading + Fitness-
Evolution) e devolve duas frases — o ESTADO (como você está) e a CONDUTA (o que
isso sugere). Sem IA, sem custo. Ver [[project_ideias_produto]] #21,
[[FitnessEvolution]] e o eixo do corpo em [[project_analise_corpo_garmin]]."""

from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
)
from app.domain.entities.fitness_evolution import (
    EVO_DECLINING,
    EVO_IMPROVING,
    EVO_STABLE,
    FitnessEvolution,
)

# buckets do corpo (semáforo de "posso puxar?")
_CORPO_GREEN = "GREEN"     # absorvendo/equilibrado/descansado
_CORPO_YELLOW = "YELLOW"   # recuperação deu uma caída
_CORPO_RED = "RED"         # carga alta + recuperação caindo → freio
_CORPO_UNKNOWN = "UNKNOWN"  # sem recuperação / sem histórico de carga

# buckets da forma
_FORMA_UP = "UP"
_FORMA_FLAT = "FLAT"
_FORMA_DOWN = "DOWN"
_FORMA_UNKNOWN = "UNKNOWN"  # sem lastro OU dado velho (parou de correr)


class StatePortraitSynthesizer:

    @staticmethod
    def synthesize(
        reading: BodyReading,
        evolution: FitnessEvolution,
    ) -> tuple[str, str]:
        """Devolve (ESTADO, CONDUTA): a frase que cruza os eixos e a que sugere
        o próximo passo. Degrada com elegância — se um eixo não tem leitura, a
        síntese fala do que existe."""

        corpo = StatePortraitSynthesizer._corpo_bucket(reading)

        forma = StatePortraitSynthesizer._forma_bucket(evolution)

        return (
            StatePortraitSynthesizer._state(corpo, forma),
            StatePortraitSynthesizer._conduct(corpo, forma),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _corpo_bucket(reading: BodyReading) -> str:

        # sem recuperação de verdade, não se lê o corpo (carga nunca é lida
        # isolada — regra do eixo do corpo)
        if not reading.recovery.has_data:

            return _CORPO_UNKNOWN

        return {
            BODY_FRESH: _CORPO_GREEN,
            BODY_BALANCED: _CORPO_GREEN,
            BODY_ABSORBING: _CORPO_GREEN,
            BODY_RECOVERY_FLAG: _CORPO_YELLOW,
            BODY_STRAINED: _CORPO_RED,
        }.get(reading.body_state, _CORPO_UNKNOWN)

    @staticmethod
    def _forma_bucket(evolution: FitnessEvolution) -> str:

        # dado velho (parou de correr) ou sem lastro: sem leitura de forma
        if evolution.stale or not evolution.has_data:

            return _FORMA_UNKNOWN

        return {
            EVO_IMPROVING: _FORMA_UP,
            EVO_STABLE: _FORMA_FLAT,
            EVO_DECLINING: _FORMA_DOWN,
        }.get(evolution.direction, _FORMA_UNKNOWN)

    # -- ESTADO (como você está, cruzando os eixos) --------------------

    @staticmethod
    def _state(corpo: str, forma: str) -> str:

        both = _STATE.get((corpo, forma))

        if both:

            return both

        # um eixo sem leitura: fala do que existe
        if corpo != _CORPO_UNKNOWN:

            return _STATE_CORPO_ONLY[corpo]

        if forma != _FORMA_UNKNOWN:

            return _STATE_FORMA_ONLY[forma]

        return (
            "Ainda estou juntando teu histórico pra um retrato completo — "
            "segue registrando teus treinos que a leitura fica cada vez melhor."
        )

    # -- CONDUTA (o que isso sugere) -----------------------------------

    @staticmethod
    def _conduct(corpo: str, forma: str) -> str:

        both = _CONDUCT.get((corpo, forma))

        if both:

            return both

        if corpo != _CORPO_UNKNOWN:

            return _CONDUCT_CORPO_ONLY[corpo]

        if forma != _FORMA_UNKNOWN:

            return _CONDUCT_FORMA_ONLY[forma]

        return "Segue no ritmo — em poucas semanas o retrato completo aparece. 👊"


# Matriz do ESTADO — a leitura cruzada (o coração do retrato). Corpo × Forma.
_STATE = {
    (_CORPO_GREEN, _FORMA_UP): (
        "Teu corpo está absorvendo bem o treino E a forma vem subindo — é a "
        "melhor combinação possível, a janela ideal pra progredir."
    ),
    (_CORPO_GREEN, _FORMA_FLAT): (
        "Corpo em dia e base firme, mas a forma estacionou — você está pronto "
        "pra um empurrão que fure o platô."
    ),
    (_CORPO_GREEN, _FORMA_DOWN): (
        "Corpo recuperado, porém a forma recuou um pouco — nada de susto, é "
        "hora de retomar o ritmo com o corpo dando espaço pra isso."
    ),
    (_CORPO_YELLOW, _FORMA_UP): (
        "Você vem evoluindo, mas a recuperação deu uma caída — cuidado pra não "
        "trocar o ganho por fadiga bem agora."
    ),
    (_CORPO_YELLOW, _FORMA_FLAT): (
        "A forma está firme, mas a recuperação pediu atenção — ela vem primeiro "
        "antes de pensar em puxar mais."
    ),
    (_CORPO_YELLOW, _FORMA_DOWN): (
        "Recuperação em baixa e forma recuando costumam andar juntas — o corpo "
        "está avisando que precisa de folga pra voltar a render."
    ),
    (_CORPO_RED, _FORMA_UP): (
        "Você evoluiu de verdade — e é justamente por isso que o corpo agora "
        "pede um respiro. Aliviar aqui PROTEGE o que você ganhou."
    ),
    (_CORPO_RED, _FORMA_FLAT): (
        "O corpo está pedindo freio (carga alta com recuperação caindo) e a "
        "forma parou — o caminho pra destravar passa por recuperar primeiro."
    ),
    (_CORPO_RED, _FORMA_DOWN): (
        "Corpo sobrecarregado e forma recuando — o recado é claro: prioridade "
        "total é recuperar, o rendimento volta depois."
    ),
}

_STATE_CORPO_ONLY = {
    _CORPO_GREEN: (
        "Teu corpo está lidando bem com o treino — carga e recuperação em "
        "ordem."
    ),
    _CORPO_YELLOW: (
        "Teu corpo está ok na carga, mas a recuperação deu uma caída que "
        "merece atenção."
    ),
    _CORPO_RED: (
        "Teu corpo está pedindo freio: a carga subiu e a recuperação está "
        "caindo junto."
    ),
}

_STATE_FORMA_ONLY = {
    _FORMA_UP: "Tua forma vem subindo — o corpo está rendendo mais pelo mesmo esforço.",
    _FORMA_FLAT: "Tua forma está estável — a base firme, sem grandes saltos.",
    _FORMA_DOWN: "Tua forma recuou um pouco no período — vale observar de perto.",
}

# Matriz da CONDUTA — o próximo passo, sempre cruzado e gradual.
_CONDUCT = {
    (_CORPO_GREEN, _FORMA_UP): (
        "🎯 Teu próximo plano já aproveita a janela: progride a dose com o "
        "corpo respondendo — sempre um degrau de cada vez. 👊"
    ),
    (_CORPO_GREEN, _FORMA_FLAT): (
        "🎯 Pra furar o platô, o plano já mira um estímulo de qualidade bem "
        "dosado (um tiro ou limiar na semana). 👊"
    ),
    (_CORPO_GREEN, _FORMA_DOWN): (
        "🎯 O plano retoma a base aeróbica com consistência — o corpo tem "
        "espaço, é remar de volta sem pressa. 👊"
    ),
    (_CORPO_YELLOW, _FORMA_UP): (
        "🎯 Mantém o que vem funcionando, mas sem subir a dose agora — deixa a "
        "recuperação normalizar pra seguir ganhando. 👊"
    ),
    (_CORPO_YELLOW, _FORMA_FLAT): (
        "🎯 Foco em recuperar (sono à frente) antes de buscar mais — o plano "
        "segura a intensidade até o sinal virar. 👊"
    ),
    (_CORPO_YELLOW, _FORMA_DOWN): (
        "🎯 Uns dias mais leves pra recuperar — é o atalho pra forma voltar a "
        "subir. 👊"
    ),
    (_CORPO_RED, _FORMA_UP): (
        "🎯 O plano alivia de propósito agora: recuperar aqui é o que "
        "transforma o esforço em ganho de verdade. 👊"
    ),
    (_CORPO_RED, _FORMA_FLAT): (
        "🎯 Prioridade é recuperar — o plano recua a carga e cuida do "
        "limitador antes de qualquer estímulo novo. 👊"
    ),
    (_CORPO_RED, _FORMA_DOWN): (
        "🎯 Freia e recupera: o plano prioriza descanso e base — o rendimento "
        "volta quando o corpo voltar. 👊"
    ),
}

_CONDUCT_CORPO_ONLY = {
    _CORPO_GREEN: "🎯 Tem espaço pra seguir progredindo — sempre gradual. 👊",
    _CORPO_YELLOW: "🎯 Cuida da recuperação antes de puxar mais. 👊",
    _CORPO_RED: "🎯 Segura a mão uns dias e prioriza recuperar. 👊",
}

_CONDUCT_FORMA_ONLY = {
    _FORMA_UP: "🎯 O plano aproveita a evolução pra progredir a dose — gradual. 👊",
    _FORMA_FLAT: "🎯 Um estímulo de qualidade bem dosado ajuda a furar o platô. 👊",
    _FORMA_DOWN: "🎯 Retomar a base com consistência traz a forma de volta. 👊",
}
