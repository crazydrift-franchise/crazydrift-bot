from fastapi import APIRouter, Request, HTTPException
from aiogram.types import Update
from app.config import settings

router = APIRouter()


@router.post("/telegram")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    bot = request.app.state.bot
    dp = request.app.state.dp

    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}


@router.post("/ak")
async def ak_webhook(request: Request):
    """Вебхук антикризисного советника."""
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.ak_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    ak_bot = request.app.state.ak_bot
    ak_dp  = request.app.state.ak_dp
    if not ak_bot or not ak_dp:
        raise HTTPException(status_code=503, detail="AK bot not initialized")

    data = await request.json()
    update = Update.model_validate(data)
    await ak_dp.feed_update(ak_bot, update)
    return {"ok": True}
