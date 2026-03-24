import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from app.database import AsyncSessionLocal
from app.repositories.lead_repo import LeadRepository
from app.repositories.faq_repo import TouchRepository, GptSettingsRepository
from app.services.ai.claude_service import generate_touch_message

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_bot: Bot | None = None


async def send_active_touches():
    """Send scheduled touches to leads by segment. Dedup: каждый touch → каждый лид только 1 раз."""
    global _bot
    if not _bot:
        return

    async with AsyncSessionLocal() as db:
        touch_repo = TouchRepository(db)
        lead_repo = LeadRepository(db)

        touches = await touch_repo.get_active_touches()

        for touch in touches:
            try:
                leads = await lead_repo.get_leads_by_segment(touch.segment)

                for lead in leads:
                    if not lead.user or not lead.user.telegram_user_id:
                        continue

                    # Проверяем не отправляли ли уже это касание этому лиду
                    from sqlalchemy import select
                    from app.models import TouchSendLog
                    already_sent = await db.scalar(
                        select(TouchSendLog.id).where(
                            TouchSendLog.touch_id == touch.id,
                            TouchSendLog.lead_id == lead.id,
                        )
                    )
                    if already_sent:
                        continue

                    # Определяем текст
                    if touch.send_mode == "static":
                        text = touch.message_text
                    elif touch.send_mode == "gpt_generate":
                        text = await generate_touch_message(
                            touch.gpt_prompt, lead.name or ""
                        )
                    else:
                        continue

                    if not text:
                        continue

                    try:
                        await _bot.send_message(
                            chat_id=lead.user.telegram_user_id,
                            text=text,
                        )
                        # Записываем лог чтобы не отправлять повторно
                        from app.models import TouchSendLog
                        db.add(TouchSendLog(touch_id=touch.id, lead_id=lead.id))

                        from app.models import EventType
                        await lead_repo.add_event(
                            lead.id, EventType.touch,
                            f"Касание «{touch.name}» — доставлено"
                        )
                        await touch_repo.increment_sent(touch.id)
                        logger.info(f"Touch '{touch.name}' sent to lead {lead.id}")
                    except Exception as e:
                        logger.warning(f"Failed to send touch to {lead.user.telegram_user_id}: {e}")

                await db.commit()

            except Exception as e:
                logger.error(f"Touch processing error for '{touch.name}': {e}")


async def send_five_minute_followup():
    """Send 5-minute follow-up to leads who received materials but haven't requested a call."""
    global _bot
    if not _bot:
        return

    from sqlalchemy import select, and_
    from app.models import Lead, LeadStatus, User
    from datetime import datetime, timedelta

    async with AsyncSessionLocal() as db:
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        cutoff_max = datetime.utcnow() - timedelta(minutes=6)

        result = await db.execute(
            select(Lead).join(User).where(
                and_(
                    Lead.status == LeadStatus.materials_sent,
                    Lead.updated_at <= cutoff,
                    Lead.updated_at >= cutoff_max,
                )
            )
        )
        leads = result.scalars().all()

        for lead in leads:
            if not lead.user:
                continue
            try:
                from app.bot.keyboards.keyboards import call_slots_keyboard
                await _bot.send_message(
                    chat_id=lead.user.telegram_user_id,
                    text="Вы уже ознакомились с материалами? 📋\n\nКогда Вам удобно принять звонок?",
                    reply_markup=call_slots_keyboard(),
                )
                from app.models import EventType
                from app.repositories.lead_repo import LeadRepository
                repo = LeadRepository(db)
                await repo.add_event(lead.id, EventType.touch, "Авто-касание: 5 минут после материалов")
                await db.commit()
            except Exception as e:
                logger.warning(f"5-min followup failed for lead {lead.id}: {e}")


async def check_task_due():
    """Notify manager about tasks due soon."""
    from sqlalchemy import select, and_
    from app.models import Task, TaskStatus, Lead
    from datetime import datetime, timedelta
    from app.services.notifications import notify_manager

    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        # Tasks due in next 30 min, not yet notified, not done
        result = await db.execute(
            select(Task).where(
                and_(
                    Task.due_at >= now,
                    Task.due_at <= now + timedelta(minutes=30),
                    Task.notified == False,
                    Task.status != TaskStatus.done,
                )
            )
        )
        for task in result.scalars().all():
            lead_name = None
            if task.lead_id:
                lead = await db.get(Lead, task.lead_id)
                lead_name = lead.name if lead else f"Лид #{task.lead_id}"
            due_str = task.due_at.strftime("%d.%m.%Y %H:%M")
            task.notified = True  # уведомление отключено
        await db.commit()


async def check_note_reminders():
    """Напоминания по заметкам: при создании (уже), за 3ч, за 1ч, в момент."""
    from sqlalchemy import select, and_
    from app.models import LeadNote, Lead
    from datetime import datetime, timedelta
    from app.services.notifications import notify_manager

    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()

        # За 3 часа — отключено
        # (п.6 отключён по запросу)
        # Помечаем как отправленные чтобы не накапливались
        window_3h = now + timedelta(hours=3)
        result = await db.execute(
            select(LeadNote).where(
                and_(
                    LeadNote.remind_at >= now,
                    LeadNote.remind_at <= window_3h + timedelta(minutes=1),
                    LeadNote.remind_3h_sent == False,
                    LeadNote.remind_at > now + timedelta(hours=2, minutes=55),
                )
            )
        )
        for note in result.scalars().all():
            note.remind_3h_sent = True

        # За 1 час
        window_1h = now + timedelta(hours=1)
        result = await db.execute(
            select(LeadNote).join(Lead).where(
                and_(
                    LeadNote.remind_at >= now,
                    LeadNote.remind_at <= window_1h + timedelta(minutes=1),
                    LeadNote.remind_1h_sent == False,
                    LeadNote.remind_at > now + timedelta(minutes=55),
                )
            )
        )
        for note in result.scalars().all():
            lead = await db.get(Lead, note.lead_id)
            name = getattr(lead, "name", None) or f"Лид #{note.lead_id}"
            remind_str = note.remind_at.strftime("%d.%m.%Y %H:%M")
            city = getattr(lead, "city", None) or "—"
            lead_link = f"https://panel-crazyfr.ru/leads/{note.lead_id}"
            await notify_manager(
                f"⏰ *Напоминание через 1 час*\n"
                f"Лид: {name}\n"
                f"Город: {city}\n"
                f"Заметка: {note.content[:200]}\n"
                f"Время: {remind_str}\n"
                f"[Открыть карточку]({lead_link})"
            )
            note.remind_1h_sent = True

        # В момент
        result = await db.execute(
            select(LeadNote).join(Lead).where(
                and_(
                    LeadNote.remind_at >= now,
                    LeadNote.remind_at <= now + timedelta(minutes=1),
                    LeadNote.remind_sent == False,
                )
            )
        )
        for note in result.scalars().all():
            lead = await db.get(Lead, note.lead_id)
            name = getattr(lead, "name", None) or f"Лид #{note.lead_id}"
            city = getattr(lead, "city", None) or "—"
            lead_link = f"https://panel-crazyfr.ru/leads/{note.lead_id}"
            await notify_manager(
                f"🔔 *Напоминание — выполнить сейчас!*\n"
                f"Лид: {name}\n"
                f"Город: {city}\n"
                f"Заметка: {note.content[:200]}\n"
                f"[Открыть карточку]({lead_link})"
            )
            note.remind_sent = True

        await db.commit()


async def check_reminders():
    """Проверяем напоминания менеджеру о лидах."""
    from sqlalchemy import select, and_
    from app.models import Lead
    from datetime import datetime, timedelta
    from app.services.notifications import notify_reminder

    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        window_end = now + timedelta(minutes=1)

        result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.reminder_at >= now,
                    Lead.reminder_at <= window_end,
                )
            )
        )
        leads = result.scalars().all()

        for lead in leads:
            await notify_reminder(
                lead.name or "—",
                lead.id,
                getattr(lead, "manager_notes", None),
                city=getattr(lead, "city", None),
            )
            # Сбрасываем напоминание после отправки
            lead.reminder_at = None
        await db.commit()


async def send_scheduled_broadcasts():
    """Send broadcasts that are scheduled for now."""
    global _bot
    if not _bot:
        return
    from app.models import Broadcast, BroadcastStatus, Lead, User
    from sqlalchemy import select
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Broadcast).where(
                Broadcast.status == BroadcastStatus.scheduled,
                Broadcast.scheduled_at <= now,
            )
        )
        broadcasts = result.scalars().all()
        for bc in broadcasts:
            sent = 0
            failed = 0
            try:
                leads_result = await db.execute(
                    select(Lead).join(User, Lead.user_id == User.id).where(User.telegram_user_id.isnot(None))
                )
                leads = leads_result.scalars().all()
                for lead in leads:
                    if not lead.user or not lead.user.telegram_user_id:
                        continue
                    if getattr(lead, "is_blocked", False):
                        continue
                    try:
                        await _bot.send_message(lead.user.telegram_user_id, bc.text, parse_mode="Markdown")
                        sent += 1
                    except Exception:
                        failed += 1
            except Exception as e:
                logger.error(f"Broadcast {bc.id} error: {e}")
                failed += 1
            bc.status = BroadcastStatus.sent
            bc.sent_at = datetime.utcnow()
            bc.sent_count = sent
            bc.failed_count = failed
            await db.commit()


async def start_scheduler(bot: Bot):
    global _bot
    _bot = bot

    scheduler.add_job(send_qual_reminders, trigger=IntervalTrigger(minutes=15), id="qual_reminders", replace_existing=True)
    scheduler.add_job(send_faq_followups, trigger=IntervalTrigger(minutes=30), id="faq_followups", replace_existing=True)
    scheduler.add_job(send_scheduled_broadcasts, trigger=IntervalTrigger(minutes=1), id="send_broadcasts", replace_existing=True)
    scheduler.add_job(send_active_touches, trigger=IntervalTrigger(hours=1), id="send_touches", replace_existing=True)
    scheduler.add_job(send_five_minute_followup, trigger=IntervalTrigger(minutes=1), id="five_min_followup", replace_existing=True)
    scheduler.add_job(check_reminders, trigger=IntervalTrigger(minutes=1), id="check_reminders", replace_existing=True)
    scheduler.add_job(check_note_reminders, trigger=IntervalTrigger(minutes=1), id="check_note_reminders", replace_existing=True)
    scheduler.add_job(check_task_due, trigger=IntervalTrigger(minutes=5), id="check_task_due", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started")


async def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
    logger.info("Scheduler stopped")


async def send_faq_followups():
    """Send FAQ follow-up messages to leads without phone after delay."""
    from sqlalchemy import select, and_
    from app.models import FaqItem, FaqFollowupLog, Lead, User, LeadEvent, EventType
    from datetime import datetime, timedelta
    import json

    async with AsyncSessionLocal() as db:
        # Get all enabled FAQ followups
        result = await db.execute(
            select(FaqItem).where(
                FaqItem.followup_enabled == True,
                FaqItem.followup_text.isnot(None),
            )
        )
        faq_items = result.scalars().all()
        if not faq_items:
            return

        for faq_item in faq_items:
            delay = timedelta(hours=faq_item.followup_delay_hours or 24)
            cutoff = datetime.utcnow() - delay

            # Find leads who viewed this FAQ item (via events), have no phone, registered before cutoff
            events_result = await db.execute(
                select(LeadEvent).where(
                    LeadEvent.event_type == EventType.faq_view,
                    LeadEvent.data.contains(str(faq_item.id)),
                )
            )
            events = events_result.scalars().all()

            for event in events:
                lead = await db.get(Lead, event.lead_id)
                if not lead:
                    continue
                if lead.phone:  # уже оставил телефон — не дожимаем
                    continue
                if lead.created_at > cutoff:  # ещё рано
                    continue
                if getattr(lead, "is_blocked", False):
                    continue

                # Check not already sent
                already = await db.execute(
                    select(FaqFollowupLog).where(
                        FaqFollowupLog.lead_id == lead.id,
                        FaqFollowupLog.faq_item_id == faq_item.id,
                    )
                )
                if already.scalars().first():
                    continue

                # Get telegram_user_id
                user = await db.get(User, lead.user_id) if lead.user_id else None
                if not user or not user.telegram_user_id:
                    continue

                # Build keyboard
                keyboard = None
                if faq_item.followup_buttons:
                    try:
                        buttons_data = json.loads(faq_item.followup_buttons)
                        # Get send time from meta button
                        meta = next((b for b in buttons_data if b.get("id") == "__meta__"), None)
                        send_time_str = meta.get("value", "10:00") if meta else "10:00"
                        # Check if current time matches send time (within 30 min window)
                        now_local = datetime.utcnow().replace(tzinfo=None)
                        # Convert UTC to Moscow (UTC+3)
                        moscow_hour = (now_local.hour + 3) % 24
                        moscow_time_str = f"{moscow_hour:02d}:{now_local.minute:02d}"
                        target_h, target_m = map(int, send_time_str.split(":"))
                        cur_minutes = moscow_hour * 60 + now_local.minute
                        target_minutes = target_h * 60 + target_m
                        if abs(cur_minutes - target_minutes) > 30:
                            continue  # Not the right time yet
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        kb = []
                        for btn in buttons_data:
                            if btn.get("id") == "__meta__":
                                continue
                            if btn.get("type") == "link":
                                kb.append([InlineKeyboardButton(
                                    text=btn["label"],
                                    url=btn.get("value", "#")
                                )])
                            elif btn.get("type") == "gpt":
                                kb.append([InlineKeyboardButton(
                                    text=btn["label"],
                                    callback_data=f"faq_gpt:{faq_item.id}:{btn.get('id', '')}"
                                )])
                        if kb:
                            keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
                    except Exception:
                        pass

                # Send
                if _bot:
                    try:
                        await _bot.send_message(
                            user.telegram_user_id,
                            faq_item.followup_text,
                            reply_markup=keyboard,
                            parse_mode="Markdown",
                        )
                        # Log
                        log = FaqFollowupLog(lead_id=lead.id, faq_item_id=faq_item.id)
                        db.add(log)
                        await db.commit()
                    except Exception as e:
                        logger.error(f"FAQ followup error: {e}")


async def send_qual_reminders():
    """Send qualification reminders to leads who postponed."""
    global _bot
    if not _bot:
        return
    try:
        import redis.asyncio as aioredis
        import json
        from app.config import settings
        from datetime import datetime
        r = aioredis.from_url(settings.redis_url)
        keys = await r.keys("qual_reminder:*")
        for key in keys:
            raw = await r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            send_at = datetime.fromisoformat(data["send_at"])
            if datetime.utcnow() < send_at:
                continue
            tg_id = data["telegram_user_id"]
            attempt = data.get("attempt", 1)
            await r.delete(key)
            # Send reminder
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, готов ответить", callback_data="qual_start")],
                [InlineKeyboardButton(text="⏰ Напомнить позже", callback_data="qual_remind_next")],
            ])
            try:
                await _bot.send_message(
                    tg_id,
                    "Вы планировали ответить на несколько вопросов о вашем бизнес-плане 📋\n\n"
                    "Готовы продолжить?",
                    reply_markup=kb,
                )
            except Exception as e:
                logger.error(f"qual reminder send error: {e}")
        await r.aclose()
    except Exception as e:
        logger.error(f"send_qual_reminders error: {e}")
