from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.chat.deps import get_repository
from app.admin.deps import require_admin

router = APIRouter(prefix="/chats/admin", tags=["admin"], dependencies=[Depends(require_admin)])

class BroadcastBody(BaseModel):
    message: str
    interface_filter: str = "telegram"

@router.get("/stats")
async def get_stats(repo=Depends(get_repository)):
    return {
        "total_messages": 42,
        "active_users": 10,
        "avg_latency_ms": 1200,
        "moderation_block_rate": 0.05,
        "feedback_up_ratio": 0.78,
    }

@router.get("/users")
async def list_users(limit: int = 50, repo=Depends(get_repository)):
    return {"users": []}

@router.post("/broadcast")
async def broadcast(body: BroadcastBody, repo=Depends(get_repository)):
    if body.interface_filter != "telegram":
        raise HTTPException(status_code=400, detail="Only telegram supported")
    return {"ok": True, "sent": 0}