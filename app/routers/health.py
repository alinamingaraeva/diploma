from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    """Простой healthcheck, всегда 200."""
    return {"status": "ok"}