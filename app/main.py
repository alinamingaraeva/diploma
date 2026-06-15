import time
import httpx
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError, LLMAuthError
from app.routers import chat, health, models

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-service")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")

    # Правильный параметр — proxy (единственное число)
    proxy_url = "http://local_user:p32kcF26NhWE@72.56.89.38:8888"
    http_client = httpx.AsyncClient(proxy=proxy_url)

    app.state.openai_client = AsyncOpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http_client,
        timeout=settings.openai.request_timeout,
        max_retries=settings.openai.max_retries,
    )

    # ... остальной код (Redis) ...
    try:
        app.state.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        await app.state.redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis not available: {e}. Caching disabled.")
        app.state.redis_client = None

    yield

    # Shutdown
    await app.state.openai_client.close()
    if app.state.redis_client:
        await app.state.redis_client.close()
    await http_client.aclose()
    logger.info("Shutdown complete")

app = FastAPI(
    title="LLM Service",
    description="Асинхронный сервис для работы с LLM (OpenAI/polza.ai) с кешированием и стримингом",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Middleware для логирования и request_id
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        f"request_id={request_id} method={request.method} path={request.url.path} "
        f"status={response.status_code} duration_ms={duration_ms:.2f}"
    )
    response.headers["X-Request-ID"] = request_id
    return response


# Обработчики исключений
@app.exception_handler(LLMRateLimitError)
async def llm_rate_limit_handler(request: Request, exc: LLMRateLimitError):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": {"code": "rate_limit", "message": str(exc)}},
    )


@app.exception_handler(LLMTimeoutError)
async def llm_timeout_handler(request: Request, exc: LLMTimeoutError):
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"error": {"code": "timeout", "message": str(exc)}},
    )


@app.exception_handler(LLMAuthError)
async def llm_auth_handler(request: Request, exc: LLMAuthError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": {"code": "auth_error", "message": str(exc)}},
    )


@app.exception_handler(LLMError)
async def llm_general_handler(request: Request, exc: LLMError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": {"code": "llm_error", "message": str(exc)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err["loc"])
        errors.append({"field": field, "message": err["msg"]})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors},
    )


# Подключаем роутеры
app.include_router(chat.router)
app.include_router(health.router)
app.include_router(models.router)