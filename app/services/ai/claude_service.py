import json
import anthropic
from app.config import settings

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
MODEL = "claude-sonnet-4-20250514"


async def _call_claude(prompt: str, max_tokens: int = 2000) -> str:
    """Base function to call Claude with a single user message."""
    msg = await client.messages.create(
        model=MODEL, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


async def ask_bot(user_message: str, system_prompt: str, knowledge_base: str) -> str:
    try:
        full_system = (
            f"{system_prompt}\n\n"
            f"=== БАЗА ЗНАНИЙ ===\n{knowledge_base}\n=== КОНЕЦ ===\n\n"
            f"Если ответа нет — скажи что уточнишь у менеджера."
        )
        msg = await client.messages.create(
            model=MODEL, max_tokens=800, system=full_system,
            messages=[{"role": "user", "content": user_message}],
        )
        return msg.content[0].text
    except Exception:
        return f"Не могу ответить прямо сейчас. Свяжитесь с менеджером: {settings.materials_manager_url}"


async def analyze_lead(lead_data: dict, analysis_prompt: str) -> dict:
    try:
        prompt = (
            f"{analysis_prompt}\n\n"
            f"Данные лида:\n{json.dumps(lead_data, ensure_ascii=False, indent=2)}\n\n"
            f"Верни ТОЛЬКО валидный JSON без markdown."
        )
        msg = await client.messages.create(
            model=MODEL, max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```")
        return json.loads(text)
    except Exception:
        return {
            "engagement_score": 30, "lead_temperature": "cold",
            "summary": "Анализ недоступен", "recommended_action": "Связаться вручную",
        }


async def analyze_leads_batch(leads_data: list[dict], period_label: str) -> dict:
    """
    Глубокий анализ стека лидов за период.
    Возвращает: сегменты, приоритеты, скрипты, рекомендации по воронке.
    """
    try:
        prompt = f"""Ты — опытный коммерческий директор, маркетолог и практик холодных продаж с огромным опытом.

Проанализируй стек лидов за период: {period_label}
Всего лидов: {len(leads_data)}

Данные по лидам:
{json.dumps(leads_data, ensure_ascii=False, indent=2)}

Сделай профессиональный анализ и верни JSON (без markdown):
{{
  "period_summary": "краткое резюме периода",
  "total_analyzed": число,
  "funnel_insights": ["вывод 1", "вывод 2", ...],
  "weak_spots": ["слабое место воронки 1", ...],
  "segments": [
    {{"name": "название сегмента", "count": число, "description": "описание", "action": "что делать"}}
  ],
  "priority_leads": [
    {{
      "lead_id": число,
      "name": "имя",
      "priority": "high/medium/low",
      "reason": "почему приоритетный",
      "contact_method": "как связаться (звонок/telegram/whatsapp)",
      "best_time": "когда лучше",
      "opening_script": "первая фраза при контакте",
      "key_objection": "главное возражение которое надо снять",
      "recommendation": "конкретная рекомендация"
    }}
  ],
  "channel_insights": "анализ по UTM источникам если есть",
  "content_insights": "что чаще всего спрашивают, какие темы волнуют",
  "recommendations": ["рекомендация 1 по воронке", "рекомендация 2", ...],
  "weekly_actions": ["действие 1 для менеджера на неделю", ...]
}}"""

        msg = await client.messages.create(
            model=MODEL, max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```")
        return json.loads(text)
    except Exception as e:
        return {"error": str(e), "period_summary": "Анализ недоступен"}


async def generate_touch_message(prompt: str, lead_name: str = "") -> str:
    try:
        full_prompt = f"{prompt}\n\nИмя клиента: {lead_name}" if lead_name else prompt
        msg = await client.messages.create(
            model=MODEL, max_tokens=300,
            messages=[{"role": "user", "content": full_prompt}],
        )
        return msg.content[0].text
    except Exception:
        return ""


async def generate_weekly_report(stats: dict) -> dict:
    try:
        prompt = (
            f"Сгенерируй еженедельный отчёт для CRM системы франшизы CrazyDrift.\n"
            f"Статистика: {json.dumps(stats, ensure_ascii=False)}\n\n"
            f"Верни JSON: {{summary: string, insights: [string], recommendations: [string], hot_leads_count: int}}"
        )
        msg = await client.messages.create(
            model=MODEL, max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```")
        return json.loads(text)
    except Exception:
        return {"summary": "Недоступно", "insights": [], "recommendations": [], "hot_leads_count": 0}
