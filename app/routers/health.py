from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    """Liveness probe: всегда возвращает 200, если процесс жив."""
    return {"status": "ok"}

@router.get("/ready")
async def readiness_check(request: Request):
    """Readiness probe: проверяет доступность Redis."""
    redis = request.app.state.redis_client
    if redis is None:
        # Если Redis не настроен (например, нет переменной REDIS_URL), считаем ready
        return {"status": "ok", "redis": "not_configured"}
    try:
        # Проверяем соединение с Redis с таймаутом 1 секунда
        await redis.ping()
        return {"status": "ok", "redis": "up"}
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "redis": "down"}
        )