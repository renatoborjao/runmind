import re

# O texto conversacional vem do Gemini em markdown padrão (**negrito**,
# bullets com "*"/"-", cabeçalhos com "#"). O Telegram, quando enviado
# sem parse_mode, mostra esses símbolos crus — foi o que deixou o plano
# "desconfigurado". Como o texto é livre, normalizamos para texto limpo
# em vez de arriscar o escape frágil do MarkdownV2/HTML.

_BOLD_DOUBLE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_UNDERSCORE = re.compile(r"__(.+?)__", re.DOTALL)
_HEADER = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_BULLET = re.compile(r"(?m)^(\s*)[*\-+]\s+")
_EMPHASIS_STAR = re.compile(r"\*(\S(?:.*?\S)?)\*")
_EMPHASIS_UNDERSCORE = re.compile(r"(?<!\w)_(\S(?:.*?\S)?)_(?!\w)")


def to_plain_text(text: str) -> str:
    """Remove marcação markdown, deixando texto legível no Telegram.

    Ordem importa: os marcadores duplos e os bullets do início de linha
    são resolvidos antes da ênfase de marcador único, para que o "*" de
    um bullet nunca seja confundido com negrito/itálico.
    """

    # negrito/itálico com marcador duplo: **x** / __x__
    text = _BOLD_DOUBLE.sub(r"\1", text)
    text = _BOLD_UNDERSCORE.sub(r"\1", text)

    # cabeçalhos "### Título" viram texto simples
    text = _HEADER.sub("", text)

    # bullets no início da linha: "* ", "- ", "+ " viram "• "
    text = _BULLET.sub(r"\1• ", text)

    # ênfase restante com marcador único: *x* / _x_
    text = _EMPHASIS_STAR.sub(r"\1", text)
    text = _EMPHASIS_UNDERSCORE.sub(r"\1", text)

    return text
