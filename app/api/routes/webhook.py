from fastapi import APIRouter, Request, HTTPException
from aiogram.types import Update
from app.config import settings

router = APIRouter()


@router.post("/telegram")
async def telegram_webhook(request: Request):
    # Validate secret
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    bot = request.app.state.bot
    dp = request.app.state.dp

    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}
