"""Registro das COBRANÇAS que o coach já fez (o "⚠️ Ponto de atenção" da
análise, a cobrança da semana) — storage/coach_attention/{profile}.json.

Treinador de verdade lembra do que já falou: cobra UMA vez, e depois só
relembra de leve ou reconhece a melhora. Sem isto, a validação de 26/09 mostrou
a mesma bronca de sono em três análises seguidas — vira sermão. As IAs recebem
as cobranças recentes e escolhem: ângulo novo, relembrar em meia linha, ou
reconhecer que o atleta corrigiu. Ver [[feedback_orientar_nao_mandar]]."""

import json
from datetime import date, timedelta
from pathlib import Path

_STORAGE = Path(__file__).resolve().parents[3] / "storage" / "coach_attention"

_MAX_ENTRIES = 30

# janela que as IAs enxergam (o que foi cobrado "há pouco")
_RECENT_DAYS = 14


class CoachAttentionLog:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def _load(profile: str) -> list[dict]:

        file = CoachAttentionLog._file(profile)

        if not file.exists():

            return []

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            return data if isinstance(data, list) else []

        except (json.JSONDecodeError, OSError):

            return []

    @staticmethod
    def record(profile: str, day: date, text: str, source: str) -> None:
        """Guarda a cobrança feita (best-effort — nunca derruba o envio)."""

        text = (text or "").strip()

        if not text:

            return

        try:

            entries = CoachAttentionLog._load(profile)

            entries.append(
                {"day": day.isoformat(), "source": source, "text": text}
            )

            _STORAGE.mkdir(parents=True, exist_ok=True)

            CoachAttentionLog._file(profile).write_text(
                json.dumps(entries[-_MAX_ENTRIES:], ensure_ascii=False, indent=1),
                encoding="utf-8",
            )

        except OSError as e:

            print(f"Registro de cobrança falhou p/ '{profile}': {e}")

    @staticmethod
    def recent(profile: str, today: date, days: int = _RECENT_DAYS) -> list[dict]:

        since = today - timedelta(days=days)

        out = []

        for entry in CoachAttentionLog._load(profile):

            try:

                if date.fromisoformat(entry["day"]) >= since:

                    out.append(entry)

            except (KeyError, ValueError, TypeError):

                continue

        return out

    @staticmethod
    def render(profile: str, today: date) -> str:
        """Bloco pro prompt: o que você JÁ cobrou dele há pouco."""

        entries = CoachAttentionLog.recent(profile, today)

        if not entries:

            return ""

        label = {"analysis": "análise de treino", "weekly": "leitura da semana"}

        lines = [
            f"- {date.fromisoformat(e['day']):%d/%m} "
            f"({label.get(e.get('source'), e.get('source'))}): {e['text']}"
            for e in entries[-6:]
        ]

        return (
            "COBRANÇAS QUE VOCÊ JÁ FEZ A ELE (últimos 14 dias) — NÃO repita a "
            "mesma bronca: se o padrão continua, relembre em meia frase ou "
            "traga um ângulo NOVO; se ele corrigiu, RECONHEÇA:\n"
            + "\n".join(lines)
        )
