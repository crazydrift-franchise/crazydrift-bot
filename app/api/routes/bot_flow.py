from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.api.routes.auth import verify_token
from app.models import BotFlow
import json

router = APIRouter()


class SaveFlow(BaseModel):
    nodes: list
    edges: list
    name: str = "main"


@router.get("/")
async def get_flow(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(BotFlow).where(BotFlow.is_active == True).order_by(BotFlow.updated_at.desc()))
    flow = result.scalars().first()
    if not flow:
        return {"nodes": [], "edges": [], "name": "main"}
    data = json.loads(flow.flow_json)
    return {"nodes": data.get("nodes", []), "edges": data.get("edges", []), "name": flow.name, "updated_at": flow.updated_at.isoformat()}


@router.post("/")
async def save_flow(body: SaveFlow, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(BotFlow).where(BotFlow.name == body.name))
    flow = result.scalars().first()
    flow_json = json.dumps({"nodes": body.nodes, "edges": body.edges})
    if flow:
        flow.flow_json = flow_json
        from datetime import datetime
        flow.updated_at = datetime.utcnow()
    else:
        flow = BotFlow(name=body.name, flow_json=flow_json)
        db.add(flow)
    await db.commit()
    return {"ok": True}
