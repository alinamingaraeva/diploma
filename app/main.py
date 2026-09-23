import time
import httpx
import uuid
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from openai import AsyncOpenAI
from redis.asyncio import Redis
from structlog.contextvars import bind_contextvars, clear_contextvars
import structlog

from app.core.config import get_settings
from app.core.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError, LLMAuthError
from app.services.vector_store import VectorStore
from app.services.rag import RAGService
from app.admin.routes import router as admin_router
from app.chat.routes import router as chat_router
from app.routers import agent, chat, documents, health, models, rag
from app.observability.tracing import setup_tracing
from app.observability.logging import setup_logging

# --- 1. Настройка structlog (до создания приложения) ---
setup_logging()
logger = structlog.get_logger()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 2. Инициализация трейсинга (ДО создания клиента OpenAI) ---
    setup_tracing(project_name="diploma-fastapi")
    logger.info("Tracing initialized")

    proxy_url = settings.http_proxy
    http_client = (
        httpx.AsyncClient(proxy=proxy_url, trust_env=False)
        if proxy_url
        else httpx.AsyncClient(trust_env=False)
    )

    app.state.openai_client = AsyncOpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http_client,
        timeout=settings.openai.request_timeout,
        max_retries=settings.openai.max_retries,
    )
    app.state.canary = secrets.token_hex(4)
    logger.info(f"Canary set: {app.state.canary}")
    # --- 4. Redis (как было) ---
    try:
        app.state.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        await app.state.redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis not available: {e}. Caching disabled.")
        app.state.redis_client = None

    app.state.vector_store = VectorStore()
    try:
        await app.state.vector_store.ensure_collection()
        logger.info("Qdrant collection ready", collection=settings.qdrant_collection)
    except Exception as e:
        logger.warning(f"Qdrant not available: {e}. Vector search disabled.")
        await app.state.vector_store.client.close()
        app.state.vector_store = None

    app.state.rag_service = None
    rag_service = RAGService()
    try:
        rag_service.build()
        app.state.rag_service = rag_service
        logger.info("RAG index ready", collection=settings.rag_collection)
    except Exception as e:
        rag_service.close()
        logger.warning(f"RAG not available: {e}")

    from app.services.agent_persistent import agent_lifespan

    try:
        async with agent_lifespan() as agent_graph:
            app.state.agent_graph = agent_graph
            logger.info("agent graph ready", backend=settings.agent_checkpointer)
            yield
    except Exception as e:
        app.state.agent_graph = None
        logger.warning(f"agent graph not available: {e}")
        yield

    # --- 5. Shutdown ---
    await app.state.openai_client.close()
    if app.state.redis_client:
        await app.state.redis_client.close()
    if app.state.vector_store:
        await app.state.vector_store.client.close()
    if getattr(app.state, "rag_service", None):
        app.state.rag_service.close()
    await http_client.aclose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="ИИ-консультант музеев Казанского Кремля",
    description="Backend чат-сервиса и Telegram-бота: стриминг, инструменты музея, модерация.",
    version="1.0.0",
    lifespan=lifespan,
)

# --- 6. CORS middleware (как было) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
# --- 7. НОВОЕ: Middleware для structlog с request_id ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Генерируем или берём request_id из заголовка
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    
    # Привязываем контекстные переменные для structlog
    bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
    )
    
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Логируем HTTP-запрос в структурированном формате
        logger.info(
            "http_request",
            status=response.status_code,
            duration_ms=duration_ms,
        )
        
        # Добавляем заголовок в ответ
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        # Очищаем контекст после запроса, чтобы данные не "перетекали"
        clear_contextvars()


# --- 8. Обработчики исключений (как были) ---
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


# --- 9. Подключаем роутеры (как было) ---
app.include_router(chat.router)
app.include_router(health.router)
app.include_router(models.router)
app.include_router(rag.router)
app.include_router(documents.router)
app.include_router(agent.router)
app.include_router(admin_router)
app.include_router(chat_router)