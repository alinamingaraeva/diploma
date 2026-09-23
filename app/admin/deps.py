from fastapi import Depends, HTTPException, Header
from app.core.config import get_settings

async def require_admin(x_admin_token: str = Header(...)):
    settings = get_settings()
    expected = settings.admin_token.get_secret_value() if hasattr(settings.admin_token, "get_secret_value") else str(settings.admin_token)
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return True