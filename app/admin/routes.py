from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.admin.deps import require_admin
from app.chat.deps import get_repository
from app.services.notifier import notify_user

router = APIRouter(prefix="/chats/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class BroadcastBody(BaseModel):
    message: str
    interface_filter: str = "telegram"


@router.get("/stats")
async def get_stats(repo=Depends(get_repository)):
    return await repo.admin_stats()


@router.get("/users")
async def list_users(limit: int = 50, repo=Depends(get_repository)):
    return {"users": await repo.list_recent_users(limit=limit)}


@router.post("/broadcast")
async def broadcast(body: BroadcastBody, repo=Depends(get_repository)):
    if body.interface_filter != "telegram":
        raise HTTPException(status_code=400, detail="Only telegram supported")
    owners = await repo.list_owner_ids("telegram")
    sent = 0
    for owner in owners:
        try:
            await notify_user(int(owner), body.message)
            sent += 1
        except Exception:
            continue
    return {"ok": True, "sent": sent}
