"""Narra a leitura do corpo pro atleta. Híbrido, igual ao resto da análise:
a IA escreve (generate_text) a partir do veredito JÁ COMPUTADO pelo builder —
não recalcula; falha/vazio cai no texto determinístico (nunca vira silêncio,
[[feedback_conversa_viva]]).

Régua não-negociável no prompt: a carga NUNCA é apresentada isolada nem como
susto; é lida à luz da recuperação. Rampa + recuperação boa = absorvendo
(tranquiliza); rampa + recuperação caindo = alerta real. Aponta o limitador
acionável. Tom de coach, curto, honesto, não médico."""

from google.genai import types

from app.application.coach.writer.health_snapshot_formatter import (
    HealthSnapshotFormatter,
)
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
from app.domain.entities.body_reading_snapshot import BodyTrajectory
from app.domain.entities.training_load import acwr_border_label
from app.infrastructure.integrations.gemini.client import generate_text

THINKING_BUDGET = 256

MAX_OUTPUT_TOKENS = 500

_LIMITER_LABEL = {
    "sono": "o sono (várias noites curtas ultimamente)",
    "fc_repouso": "a FC de repouso, que vem subindo",
    "stress": "o nível de stress, que está alto",
}

_SYSTEM_PROMPT = """Você é o coach de corrida do Ritmind. Escreva pro atleta \
uma leitura CURTA do corpo dele (WhatsApp/Telegram, tom de treinador \
experiente, sem markdown).

FORMATO OBRIGATÓRIO (seções separadas por linha em branco, NUNCA um parágrafo \
único corrido; cada seção com 1-2 frases curtas):

🩺 Leitura do corpo

⚖️ [o veredito: como o corpo está lidando com o treino, cruzando carga e \
recuperação]

❤️ [os sinais que sustentam o veredito, em linguagem de gente — sem jogar \
números crus]

🎯 [o ponto de atenção acionável desta semana; se não houver limitador, o que \
manter]

REGRA NÃO-NEGOCIÁVEL: a carga de treino NUNCA é apresentada sozinha nem como \
susto. Você recebe um VEREDITO já calculado que cruza carga E recuperação — \
narre esse veredito, não invente outro nem recalcule. Um ACWR alto com \
recuperação boa é o corpo ABSORVENDO o treino (adaptação, não sobrecarga) — \
tranquilize e seja honesto. Só é alerta quando a recuperação também está \
caindo. Se houver um limitador (ex.: sono), aponte-o como o ponto de atenção \
real. Nunca dê conselho médico; fale como coach. Não repita números crus como \
se fossem o diagnóstico — traduza pro que importa pro atleta.

TRAJETÓRIA: se os FATOS trouxerem uma linha "Trajetória", incorpore-a no bloco \
⚖️ com naturalidade (ex.: se repetindo há várias leituras, ou melhorou/piorou \
desde a última) — é o que diferencia um dia isolado de um padrão. Se não vier, \
não invente trajetória alguma.

FRONTEIRA: se os FATOS disserem que a carga está "no limite" de uma faixa, NÃO \
a apresente como salto, estouro ou susto — o ACWR é ruidoso e meio ponto \
decimal não muda a vida do atleta. Diga que a carga está na fronteira e deixe \
claro que quem decide o tom é a recuperação, não o número exato.

FATOS (calculados pelo sistema; não invente além disso):
{facts}"""


class BodyReadingWriter:

    @staticmethod
    async def write(
        reading: BodyReading,
        runner_name: str,
        trajectory: BodyTrajectory | None = None,
    ) -> str:

        prompt = _SYSTEM_PROMPT.format(
            facts=BodyReadingWriter._facts(reading, runner_name, trajectory)
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

            narrative = text.strip()

        except Exception as e:  # noqa: BLE001 — nunca vira silêncio

            print(f"Leitura do corpo (IA) falhou p/ '{runner_name}': {e}")

            narrative = BodyReadingWriter._fallback(
                reading, runner_name, trajectory
            )

        # painel factual dos números de recuperação — o veredito narra, o
        # painel MOSTRA o dado concreto por trás (camada de saúde à mostra).
        panel = HealthSnapshotFormatter.panel(reading.recovery)

        return f"{narrative}\n\n{panel}" if panel else narrative

    # ------------------------------------------------------------------

    @staticmethod
    def _facts(
        reading: BodyReading,
        runner_name: str,
        trajectory: BodyTrajectory | None = None,
    ) -> str:

        load = reading.load

        rec = reading.recovery

        lines = [f"Atleta: {runner_name}", f"VEREDITO: {reading.body_state}"]

        if reading.limiter:

            lines.append(f"Limitador principal: {reading.limiter}")

        border = acwr_border_label(load.acwr)

        acwr_desc = f"{load.acwr} ({load.status}"

        if border:

            acwr_desc += f"; {border} — fronteira, não um salto"

        acwr_desc += ")"

        lines.append(
            f"Carga (ponderada por intensidade): aguda {load.acute_load} vs "
            f"crônica {load.chronic_load}, ACWR {acwr_desc}; "
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

        # números que a PRÓPRIA Garmin computou (relógio melhor) — quando vêm,
        # são mais autoritativos que os derivados; a narração deve preferi-los
        garmin = BodyReadingWriter._garmin_facts(rec)

        if garmin:

            lines.append(garmin)

        # trajetória só entra quando há notícia de verdade (o analisador já
        # decidiu isso: entrou/saiu de alerta ou segue em alerta)
        if trajectory is not None and trajectory.has_note:

            lines.append(f"Trajetória: {trajectory.athlete_note}")

        return "\n".join(lines)

    @staticmethod
    def _garmin_facts(rec) -> str | None:
        """Números que a própria Garmin calculou (readiness/status/nota de
        sono) — a narração deve preferi-los ao derivado. None se o relógio não
        computa nenhum (ex.: FR165)."""

        parts = []

        if rec.readiness_score is not None:

            parts.append(f"prontidão {rec.readiness_score}/100")

        if rec.training_status:

            parts.append(f"training status {rec.training_status}")

        if rec.hrv_status:

            parts.append(f"HRV status {rec.hrv_status}")

        if rec.sleep_score is not None:

            parts.append(f"nota de sono {rec.sleep_score}/100")

        if not parts:

            return None

        return (
            "Números da PRÓPRIA Garmin (prefira estes ao derivado): "
            + ", ".join(parts)
        )

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
    def _fallback(
        reading: BodyReading,
        runner_name: str,
        trajectory: BodyTrajectory | None = None,
    ) -> str:
        """Mesma estrutura visual da via IA (título + seções), pra o atleta
        nunca notar que a IA caiu."""

        verdict = {
            BODY_ABSORBING: (
                f"{runner_name}, você subiu o volume, mas seu corpo está "
                "absorvendo bem — recuperação em ordem. Isso é adaptação, não "
                "sobrecarga."
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

        # carga na fronteira de uma faixa: de-dramatiza o número (meio ponto
        # de ACWR não é salto), só nos estados em que a carga está elevada
        border = acwr_border_label(reading.load.acwr)

        if border and reading.body_state in (BODY_STRAINED, BODY_ABSORBING):

            verdict = (
                f"{verdict} A carga está no limite da faixa, não deu salto — "
                "o que pesa aqui é a recuperação."
            )

        # a trajetória entra colada no veredito (mesmo bloco ⚖️)
        if trajectory is not None and trajectory.has_note:

            verdict = f"{verdict} {trajectory.athlete_note}"

        lines = ["🩺 Leitura do corpo", "", f"⚖️ {verdict}"]

        signals = BodyReadingWriter._fallback_signals(reading)

        if signals:

            lines.extend(["", f"❤️ {signals}"])

        limiter = _LIMITER_LABEL.get(reading.limiter or "")

        if limiter:

            # labels começam com artigo ("o sono"/"a FC...") -> "no"/"na"
            lines.extend(["", f"🎯 Fica de olho n{limiter}."])

        return "\n".join(lines)

    @staticmethod
    def _fallback_signals(reading: BodyReading) -> str | None:
        """Sinais em linguagem simples pro bloco ❤️ (sem números crus)."""

        rec = reading.recovery

        if not rec.has_data:

            return None

        parts = []

        if rec.hrv_direction:

            parts.append(f"HRV {BodyReadingWriter._hrv_word(rec.hrv_direction)}")

        if rec.rhr_direction:

            parts.append(
                f"FC de repouso {BodyReadingWriter._rhr_word(rec.rhr_direction)}"
            )

        if rec.sleep_avg_hours is not None:

            parts.append(f"sono médio de {rec.sleep_avg_hours}h")

        if not parts:

            return None

        # "; " porque cada parte já carrega vírgula ("subindo, bom sinal")
        return f"{'; '.join(parts)}."
