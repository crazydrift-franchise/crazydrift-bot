from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel
from app.config import settings
import json

router = APIRouter()
security = HTTPBearer()

SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
SESSIONS_KEY = "admin_sessions"


class LoginRequest(BaseModel):
    login: str
    password: str


class SetManagerChat(BaseModel):
    chat_id: str


class SetApiKey(BaseModel):
    api_key: str


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        return jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def _get_redis():
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.redis_url)


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    if body.login != settings.admin_login or body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": body.login, "role": "admin"})
    try:
        r = await _get_redis()
        ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "unknown")
        ua = request.headers.get("User-Agent", "")
        device = "Мобильный" if "Mobile" in ua or "iPhone" in ua else "ПК"
        session = {
            "login": body.login, "ip": ip, "device": device, "ua": ua[:100],
            "logged_in_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        }
        sessions_raw = await r.get(SESSIONS_KEY)
        sessions = json.loads(sessions_raw) if sessions_raw else []
        sessions = [s for s in sessions if s.get("ip") != ip]
        sessions.append(session)
        await r.setex(SESSIONS_KEY, TOKEN_EXPIRE_HOURS * 3600, json.dumps(sessions))
        await r.aclose()
    except Exception:
        pass
    return {"access_token": token, "token_type": "bearer"}


@router.post("/heartbeat")
async def heartbeat(request: Request, payload: dict = Depends(verify_token)):
    try:
        r = await _get_redis()
        ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "unknown")
        sessions_raw = await r.get(SESSIONS_KEY)
        sessions = json.loads(sessions_raw) if sessions_raw else []
        for s in sessions:
            if s.get("ip") == ip:
                s["last_seen"] = datetime.utcnow().isoformat()
        await r.setex(SESSIONS_KEY, TOKEN_EXPIRE_HOURS * 3600, json.dumps(sessions))
        await r.aclose()
    except Exception:
        pass
    return {"ok": True}


@router.get("/sessions")
async def get_sessions(_=Depends(verify_token)):
    try:
        r = await _get_redis()
        sessions_raw = await r.get(SESSIONS_KEY)
        sessions = json.loads(sessions_raw) if sessions_raw else []
        await r.aclose()
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        return [s for s in sessions if datetime.fromisoformat(s["last_seen"]) >= cutoff]
    except Exception:
        return []


@router.post("/set-manager-chat")
async def set_manager_chat(body: SetManagerChat, _=Depends(verify_token)):
    try:
        r = await _get_redis()
        await r.set("manager_chat_id", body.chat_id)
        await r.aclose()
        try:
            settings.manager_chat_id = int(body.chat_id)
        except Exception:
            pass
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


@router.post("/set-api-key")
async def set_api_key(body: SetApiKey, _=Depends(verify_token)):
    try:
        r = await _get_redis()
        await r.set("anthropic_api_key", body.api_key)
        await r.aclose()
        try:
            settings.anthropic_api_key = body.api_key
            from app.services.ai import claude_service
            import anthropic
            claude_service.client = anthropic.AsyncAnthropic(api_key=body.api_key)
        except Exception:
            pass
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


@router.post("/test-notification")
async def test_notification(_=Depends(verify_token)):
    from app.services.notifications import notify_manager
    await notify_manager("🔔 Тестовое уведомление. Панель CrazyDrift работает.")
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, payload: dict = Depends(verify_token)):
    try:
        r = await _get_redis()
        ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "unknown")
        sessions_raw = await r.get(SESSIONS_KEY)
        sessions = json.loads(sessions_raw) if sessions_raw else []
        sessions = [s for s in sessions if s.get("ip") != ip]
        await r.setex(SESSIONS_KEY, TOKEN_EXPIRE_HOURS * 3600, json.dumps(sessions))
        await r.aclose()
    except Exception:
        pass
    return {"ok": True}


@router.get("/me")
async def me(payload: dict = Depends(verify_token)):
    return {"login": payload.get("sub"), "role": payload.get("role")}
