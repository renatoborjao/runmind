"""Narra a leitura do corpo pro atleta. Híbrido, igual ao resto da análise:
a IA escreve (generate_text) a partir do veredito JÁ COMPUTADO pelo builder —
não recalcula; falha/vazio cai no texto determinístico (nunca vira silêncio,
[[feedback_conversa_viva]]).

Régua não-negociável no prompt: a carga NUNCA é apresentada isolada nem como
susto; é lida à luz da recuperação. Rampa + recuperação boa = absorvendo
(tranquiliza); rampa + recuperação caindo = alerta real. Aponta o limitador
acionável. Tom de coach, curto, honesto, não médico."""

from google.genai import types

from app.core.config import get_settings
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_BUILDING,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    RISING,
    BodyReading,
)
from app.infrastructure.integrations.gemini.client import generate_text

THINKING_BUDGET = 256

MAX_OUTPUT_TOKENS = 500

_LIMITER_LABEL = {
    "sono": "o sono (várias noites curtas ultimamente)",
    "fc_repouso": "a FC de repouso, que vem subindo",
    "stress": "o nível de stress, que está alto",
}

_SYSTEM_PROMPT = """Você é o coach de corrida do RunMind. Escreva pro atleta \
uma leitura CURTA do corpo dele (WhatsApp, 2-4 frases, tom de treinador \
experiente, sem markdown, pode 1 emoji).

REGRA NÃO-NEGOCIÁVEL: a carga de treino NUNCA é apresentada sozinha nem como \
susto. Você recebe um VEREDITO já calculado que cruza carga E recuperação — \
narre esse veredito, não invente outro nem recalcule. Um ACWR alto com \
recuperação boa é o corpo ABSORVENDO o treino (adaptação, não sobrecarga) — \
tranquilize e seja honesto. Só é alerta quando a recuperação também está \
caindo. Se houver um limitador (ex.: sono), aponte-o como o ponto de atenção \
real. Nunca dê conselho médico; fale como coach. Não repita números crus como \
se fossem o diagnóstico — traduza pro que importa pro atleta.

FATOS (calculados pelo sistema; não invente além disso):
{facts}"""


class BodyReadingWriter:

    @staticmethod
    async def write(reading: BodyReading, runner_name: str) -> str:

        prompt = _SYSTEM_PROMPT.format(
            facts=BodyReadingWriter._facts(reading, runner_name)
        )

        try:

            text = await generate_text(
                model=get_settings().gemini_coach_model,
                contents=[{"role": "user", "parts": [{"text": "Como está meu corpo?"}]}],
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=THINKING_BUDGET,
                    ),
                ),
                require_text=True,
            )

            return text.strip()

        except Exception as e:  # noqa: BLE001 — nunca vira silêncio

            print(f"Leitura do corpo (IA) falhou p/ '{runner_name}': {e}")

            return BodyReadingWriter._fallback(reading, runner_name)

    # ------------------------------------------------------------------

    @staticmethod
    def _facts(reading: BodyReading, runner_name: str) -> str:

        load = reading.load

        rec = reading.recovery

        lines = [f"Atleta: {runner_name}", f"VEREDITO: {reading.body_state}"]

        if reading.limiter:

            lines.append(f"Limitador principal: {reading.limiter}")

        lines.append(
            f"Carga (ponderada por intensidade): aguda {load.acute_load} vs "
            f"crônica {load.chronic_load}, ACWR {load.acwr} ({load.status}); "
            f"semanas {load.weekly_loads}"
        )

        if rec.has_data:

            lines.append(
                "Recuperação: "
                f"HRV {rec.hrv_recent} ({BodyReadingWriter._hrv_word(rec.hrv_direction)}), "
                f"FC repouso {rec.rhr_recent} ({BodyReadingWriter._rhr_word(rec.rhr_direction)}), "
                f"sono médio {rec.sleep_avg_hours}h "
                f"({rec.short_nights} de {rec.nights_counted} noites curtas), "
                f"stress médio {rec.stress_avg}, VO2max {rec.vo2max}"
            )

        else:

            lines.append("Recuperação: sem dados do Garmin ainda")

        return "\n".join(lines)

    @staticmethod
    def _hrv_word(direction: str) -> str:

        return {
            RISING: "subindo, bom sinal",
            FALLING: "caindo, atenção",
        }.get(direction, "estável")

    @staticmethod
    def _rhr_word(direction: str) -> str:
        # direção em POV de recuperação: RISING=melhora (bpm caindo)
        return {
            RISING: "caindo, bom sinal",
            FALLING: "subindo, atenção",
        }.get(direction, "estável")

    @staticmethod
    def _fallback(reading: BodyReading, runner_name: str) -> str:

        limiter = _LIMITER_LABEL.get(reading.limiter or "")

        tail = f" Fica de olho n{limiter[1:]}" if limiter else ""

        base = {
            BODY_ABSORBING: (
                f"{runner_name}, você subiu o volume, mas seu corpo está "
                "absorvendo bem — recuperação em ordem. Isso é adaptação, não "
                "sobrecarga. Segue firme. 💪"
            ),
            BODY_BALANCED: (
                "Carga e recuperação em equilíbrio — você está no ponto. "
                "Segue assim."
            ),
            BODY_FRESH: (
                "Você está bem recuperado e com a carga leve — tem espaço pra "
                "puxar quando quiser."
            ),
            BODY_STRAINED: (
                f"{runner_name}, a carga subiu e seu corpo está dando sinal de "
                "cansaço (recuperação caindo). Vale segurar um pouco os "
                "próximos dias."
            ),
            BODY_RECOVERY_FLAG: (
                "Sua carga de treino está tranquila, mas a recuperação deu uma "
                "caída. Cuida disso antes de puxar."
            ),
            BODY_BUILDING: (
                "Ainda estou juntando seu histórico pra ler sua carga direito, "
                "mas seguimos acompanhando seu corpo de perto."
            ),
        }.get(reading.body_state, "Seguimos acompanhando seu corpo.")

        return base + tail
