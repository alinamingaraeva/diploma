import structlog
from structlog.contextvars import merge_contextvars

def setup_logging(level: str = "INFO") -> None:
    """Настраивает structlog для вывода JSON-логов с контекстными переменными."""
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )