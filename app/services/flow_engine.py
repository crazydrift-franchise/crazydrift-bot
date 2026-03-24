"""
Flow Engine — читает воронку из БД и выполняет её для лида.
Используется как замена хардкода в lead_handler.py.
"""
import json
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

_flow_cache: dict | None = None
_flow_cache_ts: float = 0
CACHE_TTL = 30  # секунд


async def get_active_flow() -> dict | None:
    """Load active flow from DB with cache."""
    import time
    global _flow_cache, _flow_cache_ts
    now = time.time()
    if _flow_cache and (now - _flow_cache_ts) < CACHE_TTL:
        return _flow_cache
    try:
        from app.database import AsyncSessionLocal
        from app.models import BotFlow
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(BotFlow).where(BotFlow.is_active == True).order_by(BotFlow.updated_at.desc())
            )
            flow = result.scalars().first()
            if not flow:
                return None
            data = json.loads(flow.flow_json)
            _flow_cache = data
            _flow_cache_ts = now
            return data
    except Exception as e:
        logger.error(f"Flow engine error: {e}")
        return None


def find_node(flow: dict, node_id: str) -> dict | None:
    """Find node by ID in flow."""
    return next((n for n in flow.get("nodes", []) if n["id"] == node_id), None)


def find_start_node(flow: dict) -> dict | None:
    """Find the start node (first node with no incoming edges or node with id='start')."""
    start = find_node(flow, "start")
    if start:
        return start
    nodes = flow.get("nodes", [])
    edges = flow.get("edges", [])
    target_ids = {e["to"] for e in edges}
    for node in nodes:
        if node["id"] not in target_ids:
            return node
    return nodes[0] if nodes else None


def get_next_node_id(flow: dict, from_node_id: str, btn_id: str | None = None) -> str | None:
    """Get next node ID given current node and optionally which button was pressed."""
    for edge in flow.get("edges", []):
        if edge["from"] == from_node_id:
            if btn_id is None or edge.get("from_btn") == btn_id or edge.get("from_btn") is None:
                return edge["to"]
    return None


def build_keyboard(node: dict) -> InlineKeyboardMarkup | None:
    """Build inline keyboard from node buttons."""
    buttons = node.get("buttons", [])
    if not buttons:
        return None
    kb = []
    for btn in buttons:
        kb.append([InlineKeyboardButton(
            text=btn["label"],
            callback_data=f"flow_btn:{node['id']}:{btn['id']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def send_flow_node(bot: Bot, telegram_user_id: int, node: dict):
    """Send a flow node message to user."""
    text = node.get("text") or node.get("label", "")
    if not text:
        return
    keyboard = build_keyboard(node)
    try:
        await bot.send_message(
            telegram_user_id,
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"send_flow_node error: {e}")


async def handle_flow_start(bot: Bot, telegram_user_id: int) -> bool:
    """Handle /start command via flow. Returns True if flow was used."""
    flow = await get_active_flow()
    if not flow or not flow.get("nodes"):
        return False
    start_node = find_start_node(flow)
    if not start_node:
        return False
    await send_flow_node(bot, telegram_user_id, start_node)
    # Save current node to Redis
    await _set_user_node(telegram_user_id, start_node["id"])
    return True


async def handle_flow_callback(bot: Bot, telegram_user_id: int, node_id: str, btn_id: str) -> bool:
    """Handle button press in flow. Returns True if flow handled it."""
    flow = await get_active_flow()
    if not flow:
        return False
    next_id = None
    # First try to find edge from this node with this btn
    for edge in flow.get("edges", []):
        if edge["from"] == node_id and edge.get("from_btn") == btn_id:
            next_id = edge["to"]
            break
    # Fallback: any edge from this node
    if not next_id:
        for edge in flow.get("edges", []):
            if edge["from"] == node_id:
                next_id = edge["to"]
                break
    if not next_id:
        return False
    next_node = find_node(flow, next_id)
    if not next_node:
        return False
    await send_flow_node(bot, telegram_user_id, next_node)
    await _set_user_node(telegram_user_id, next_id)
    return True


async def handle_flow_message(bot: Bot, telegram_user_id: int) -> bool:
    """Handle free text message — advance flow to next node. Returns True if handled."""
    flow = await get_active_flow()
    if not flow:
        return False
    current_node_id = await _get_user_node(telegram_user_id)
    if not current_node_id:
        return False
    next_id = get_next_node_id(flow, current_node_id)
    if not next_id:
        return False
    next_node = find_node(flow, next_id)
    if not next_node:
        return False
    await send_flow_node(bot, telegram_user_id, next_node)
    await _set_user_node(telegram_user_id, next_id)
    return True


async def _set_user_node(telegram_user_id: int, node_id: str):
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.redis_url)
        await r.setex(f"flow_node:{telegram_user_id}", 86400, node_id)
        await r.aclose()
    except Exception:
        pass


async def _get_user_node(telegram_user_id: int) -> str | None:
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.redis_url)
        val = await r.get(f"flow_node:{telegram_user_id}")
        await r.aclose()
        return val.decode() if val else None
    except Exception:
        return None
