from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.api.routes.auth import verify_token
import httpx

router = APIRouter()

WEBHOOK_KEY = "outbound_webhook_url"
WEBHOOK_EVENTS_KEY = "outbound_webhook_events"


async def _get_redis():
    import redis.asyncio as aioredis
    from app.config import settings
    return aioredis.from_url(settings.redis_url)


class WebhookConfig(BaseModel):
    url: str
    events: list[str] = ["new_lead", "phone_received", "call_requested"]


@router.get("/config")
async def get_webhook_config(_=Depends(verify_token)):
    try:
        r = await _get_redis()
        url = await r.get(WEBHOOK_KEY)
        events = await r.get(WEBHOOK_EVENTS_KEY)
        await r.aclose()
        import json
        return {
            "url": url.decode() if url else "",
            "events": json.loads(events) if events else ["new_lead", "phone_received", "call_requested"],
        }
    except Exception:
        return {"url": "", "events": ["new_lead", "phone_received", "call_requested"]}


@router.post("/config")
async def save_webhook_config(body: WebhookConfig, _=Depends(verify_token)):
    import json
    r = await _get_redis()
    await r.set(WEBHOOK_KEY, body.url)
    await r.set(WEBHOOK_EVENTS_KEY, json.dumps(body.events))
    await r.aclose()
    return {"ok": True}


@router.post("/test")
async def test_webhook(body: WebhookConfig, _=Depends(verify_token)):
    try:
        async with httpx.AsyncClient(timeout=5, proxies=None) as client:
            resp = await client.post(body.url, json={"event": "test", "message": "CrazyDrift webhook test"})
            return {"ok": True, "status": resp.status_code}
    except Exception as e:
        raise HTTPException(400, str(e))


async def fire_webhook(event: str, data: dict):
    """Call from bot handlers to fire outbound webhook."""
    try:
        r = await _get_redis()
        url = await r.get(WEBHOOK_KEY)
        events_raw = await r.get(WEBHOOK_EVENTS_KEY)
        await r.aclose()
        if not url:
            return
        import json
        events = json.loads(events_raw) if events_raw else []
        if event not in events:
            return
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url.decode(), json={"event": event, **data})
    except Exception:
        pass
