"""Portão barato: a mensagem é uma pergunta sobre o HISTÓRICO de período
("quantos km em maio?", "como foi meu treino em junho?", "corri mais mês
passado?")? Quando sim, o contexto do coach ganha o digest mensal pra ele
responder com verdade. Fora disso, o digest NÃO entra — o prompt do chat fica
enxuto (o único lever real de token é o prompt do chat). Só palavra-chave, sem
IA. Ver [[project_consumo_tokens]] e o MonthlyTrainingDigest."""

import re
import unicodedata

# meses por extenso (sem acento — a normalização tira acento)
_MONTHS = (
    r"janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|"
    r"outubro|novembro|dezembro"
)

_PATTERNS = [
    # cita um mês por nome ("em maio", "treino de junho")
    rf"\b({_MONTHS})\b",
    # recorte temporal relativo ("mês passado", "meses atrás", "este mês")
    r"\bmes(es)? (passado|passados|atras|anterior|anteriores)\b",
    r"\b(este|esse|neste|nesse|no) mes\b",
    r"\bpor mes\b",
    r"\bultimos? (meses|\d+ meses)\b",
    # agregação de volume/contagem sobre um período
    r"\bquant(os|as)\b.*\b(km|quilometros|corridas|treinos|vezes)\b",
    r"\bcorri\b.*\b(em|no|neste|nesse|mes|mais)\b",
    r"\b(total|media) de (km|quilometros|corridas|treinos)\b",
    # citação de ano ("em 2025", "esse ano", "ano passado")
    r"\b(19|20)\d{2}\b",
    r"\b(este|esse|neste|nesse) ano\b",
    r"\bano (passado|anterior)\b",
    # menção explícita a histórico
    r"\bhistorico\b",
]

_REGEXES = [re.compile(p) for p in _PATTERNS]


class HistoryQueryDetector:

    @staticmethod
    def looks_historical(text: str) -> bool:

        normalized = HistoryQueryDetector._normalize(text)

        return any(rx.search(normalized) for rx in _REGEXES)

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = (text or "").lower().strip()

        without = "".join(
            c
            for c in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(c) != "Mn"
        )

        return re.sub(r"\s+", " ", without)
