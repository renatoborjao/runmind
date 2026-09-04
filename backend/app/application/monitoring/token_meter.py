"""Medidor de tokens/chamadas do Gemini por atleta (observação de consumo).

Um contextvar carrega o ATLETA + rótulo da operação corrente (chat, plano,
análise, briefing...). O client do Gemini chama `record()` em cada chamada
bem-sucedida, lendo esse contexto pra atribuir os tokens ao atleta certo — sem
precisar threadar `profile` por toda chamada. Best-effort: NUNCA derruba a
chamada ao Gemini. Ver [[project_consumo_tokens]]."""

import contextlib
from contextvars import ContextVar
from datetime import UTC, datetime

from app.infrastructure.persistence.token_usage_repository import (
    TokenUsageRepository,
)

_DEFAULT = {"profile": "unknown", "label": "unknown"}

_scope: ContextVar[dict] = ContextVar("gemini_usage_scope", default=_DEFAULT)


class TokenMeter:

    @staticmethod
    @contextlib.contextmanager
    def scope(profile: str, label: str = "unknown"):
        """Marca o atleta+rótulo da operação. Tudo que chamar o Gemini dentro
        deste bloco (mesma task async) é atribuído a ele."""

        token = _scope.set(
            {"profile": profile or "unknown", "label": label or "unknown"}
        )

        try:

            yield

        finally:

            _scope.reset(token)

    @staticmethod
    def set_current(profile: str, label: str = "unknown") -> None:
        """Seta o escopo pra a TASK atual (sem reset) — pra usar no topo dos
        handlers de evento (chat, análise, plano, briefing), onde envolver o
        corpo todo num `with` seria intrusivo. Cada evento roda na sua task, e
        o contextvar é task-local, então não vaza entre eventos."""

        _scope.set(
            {"profile": profile or "unknown", "label": label or "unknown"}
        )

    @staticmethod
    def record(model: str, usage) -> None:
        """Grava 1 chamada ao Gemini (tokens de entrada/saída/raciocínio),
        atribuída ao escopo atual. Best-effort: qualquer erro é engolido."""

        try:

            if usage is None:

                return

            in_t = int(getattr(usage, "prompt_token_count", None) or 0)

            out_t = int(getattr(usage, "candidates_token_count", None) or 0)

            thoughts = int(getattr(usage, "thoughts_token_count", None) or 0)

            total = int(
                getattr(usage, "total_token_count", None) or (in_t + out_t + thoughts)
            )

            scope = _scope.get()

            record = {
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "profile": scope.get("profile", "unknown"),
                "label": scope.get("label", "unknown"),
                "model": model,
                "in": in_t,
                "out": out_t,
                "thoughts": thoughts,
                "total": total,
            }

            TokenUsageRepository().append(record["profile"], record)

        except Exception as e:  # noqa: BLE001 — medidor nunca derruba a chamada

            print(f"TokenMeter.record falhou: {e}")

    @staticmethod
    def report(profile: str) -> dict:
        """Agrega o consumo de um atleta: totais + por modelo, por rótulo e por
        dia. Lido via GET /debug/usage/{profile}."""

        records = TokenUsageRepository().read(profile)

        agg = {
            "profile": profile,
            "calls": len(records),
            "in": 0,
            "out": 0,
            "thoughts": 0,
            "total": 0,
            "by_model": {},
            "by_label": {},
            "by_day": {},
        }

        for r in records:

            agg["in"] += r.get("in", 0)

            agg["out"] += r.get("out", 0)

            agg["thoughts"] += r.get("thoughts", 0)

            agg["total"] += r.get("total", 0)

            TokenMeter._bump(agg["by_model"], r.get("model", "?"), r)

            TokenMeter._bump(agg["by_label"], r.get("label", "?"), r)

            TokenMeter._bump(agg["by_day"], (r.get("ts") or "")[:10], r)

        return agg

    @staticmethod
    def _bump(bucket: dict, key: str, r: dict) -> None:

        cell = bucket.setdefault(key, {"calls": 0, "total": 0})

        cell["calls"] += 1

        cell["total"] += r.get("total", 0)
