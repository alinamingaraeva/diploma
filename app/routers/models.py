from fastapi import APIRouter
from app.schemas.models import get_models

router = APIRouter(prefix="/models", tags=["models"])

@router.get("")
async def list_models():
    """Возвращает статический список поддерживаемых моделей."""
    return {"models": get_models()}