from fastapi import Depends, HTTPException, Header
from app.core.config import get_settings

async def require_admin(x_admin_token: str = Header(...)):
    settings = get_settings()
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return True