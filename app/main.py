import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from app.config import settings
from app.database import init_db
from app.bot.handlers import lead_handler, faq_handler, qualification_handler
from app.bot2.handlers import main_handler as ak_handler
from app.api.routes import leads, faq, knowledge, touches, gpt_settings, analytics, auth, webhook, notes, tasks, broadcasts, bot_flow, outbound_webhook, recommendations
from app.tasks.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot: Bot | None = None
dp: Dispatcher | None = None
ak_bot: Bot | None = None
ak_dp: Dispatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, dp, ak_bot, ak_dp

    # Init DB
    await init_db()
    logger.info("Database initialized")

    # Init bot
    bot = Bot(token=settings.bot_token)
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Register handlers
    dp.include_router(lead_handler.router)
    dp.include_router(qualification_handler.router)
    dp.include_router(faq_handler.router)

    from app.services import notifications
    notifications.set_bot(bot)
    await notifications.load_manager_chat_id()

    # Load API key from Redis if saved via UI
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        api_key = await r.get("anthropic_api_key")
        if api_key:
            settings.anthropic_api_key = api_key.decode()
            from app.services.ai import claude_service
            import anthropic
            claude_service.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        await r.aclose()
    except Exception:
        pass

    # Set webhook
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret,
        allowed_updates=["message", "callback_query"],
    )
    logger.info(f"Webhook set: {settings.webhook_url}")

    # Start scheduler
    await start_scheduler(bot)
    logger.info("Scheduler started")

    app.state.bot = bot
    app.state.dp = dp

    # ── Антикризисный советник (bot2) ────────────────────────────────────────
    if settings.ak_bot_token:
        from app.models import bot2_models  # ensure tables registered
        ak_bot = Bot(token=settings.ak_bot_token)
        ak_storage = RedisStorage.from_url(settings.redis_url)
        ak_dp = Dispatcher(storage=ak_storage)
        ak_dp.include_router(ak_handler.router)

        from app.services import bot2_notifications
        bot2_notifications.set_bot(ak_bot)

        await ak_bot.set_webhook(
            url=settings.ak_webhook_url,
            secret_token=settings.ak_webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        app.state.ak_bot = ak_bot
        app.state.ak_dp  = ak_dp
        logger.info(f"AK bot webhook set: {settings.ak_webhook_url}")
    else:
        app.state.ak_bot = None
        app.state.ak_dp  = None
        logger.info("AK bot token not set — skipped")

    yield

    # Cleanup
    await stop_scheduler()
    await bot.delete_webhook()
    await bot.session.close()
    if ak_bot:
        await ak_bot.delete_webhook()
        await ak_bot.session.close()
    logger.info("Bot shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="CrazyDrift API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(leads.router, prefix="/api/leads", tags=["leads"])
    app.include_router(faq.router, prefix="/api/faq", tags=["faq"])
    app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
    app.include_router(touches.router, prefix="/api/touches", tags=["touches"])
    app.include_router(gpt_settings.router, prefix="/api/gpt", tags=["gpt"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(notes.router, prefix="/api/leads", tags=["notes"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(broadcasts.router, prefix="/api/broadcasts", tags=["broadcasts"])
    app.include_router(bot_flow.router, prefix="/api/bot-flow", tags=["bot_flow"])
    app.include_router(outbound_webhook.router, prefix="/api/outbound-webhook", tags=["outbound_webhook"])
    app.include_router(recommendations.router, prefix="/api/recommendations", tags=["recommendations"])
    app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
