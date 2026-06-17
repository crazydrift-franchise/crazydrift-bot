import json
import anthropic
from app.config import settings

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """Ты — антикризисный советник для малого бизнеса в России.

ПРАВИЛА:
1. Отвечай конкретно: 3–5 actionable шагов, не общие фразы
2. Учитывай российскую реальность: аренда, ФНС, Трудовой кодекс, банки РФ
3. По юридическим и налоговым вопросам — давай направление, но рекомендуй проконсультироваться со специалистом
4. Будь поддерживающим, но реалистичным — не обнадёживай без оснований
5. Формат: короткие абзацы, конкретные цифры и сроки там где возможно
6. Объём ответа: 150–250 слов, не больше
7. Не используй markdown-таблицы, только текст и абзацы
"""

_SIGNAL_PROMPT = """Проанализируй это сообщение предпринимателя.
Верни ТОЛЬКО валидный JSON (без markdown, без пояснений):
{{
  "tired_business": true/false,
  "has_capital": true/false,
  "wants_alternative": true/false,
  "asked_franchise": true/false
}}

Критерии:
- tired_business: пишет что устал от бизнеса, хочет закрыть, «исчерпал», «надоело»
- has_capital: упоминает свободные деньги, сбережения, «есть средства», конкретные суммы от 3 млн
- wants_alternative: ищет другое направление, хочет сменить нишу, «что-то новое»
- asked_franchise: спрашивает о франшизах, готовых бизнес-моделях, «купить бизнес»

Сообщение: "{message}"
"""


async def get_antikrizis_advice(
    user_message: str,
    business_context: str,
    section_title: str,
) -> str:
    try:
        context_block = f"\nКонтекст бизнеса пользователя: {business_context}" if business_context else ""
        system = _SYSTEM_PROMPT + context_block

        msg = await client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=system,
            messages=[{
                "role": "user",
                "content": (
                    f"Раздел: {section_title}\n\n"
                    f"Вопрос пользователя: {user_message}"
                ),
            }],
        )
        return msg.content[0].text
    except Exception:
        return (
            "Не могу ответить прямо сейчас. "
            "Попробуйте позже или задайте вопрос в свободной форме."
        )


async def detect_transition_signals(message: str) -> dict:
    """Возвращает {tired_business, has_capital, wants_alternative, asked_franchise}."""
    try:
        prompt = _SIGNAL_PROMPT.format(message=message[:800])
        msg = await client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```")
        result = json.loads(text)
        return {
            "tired_business":    bool(result.get("tired_business")),
            "has_capital":       bool(result.get("has_capital")),
            "wants_alternative": bool(result.get("wants_alternative")),
            "asked_franchise":   bool(result.get("asked_franchise")),
        }
    except Exception:
        return {
            "tired_business": False,
            "has_capital": False,
            "wants_alternative": False,
            "asked_franchise": False,
        }
