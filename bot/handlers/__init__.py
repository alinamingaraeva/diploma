from .commands import router as commands_router
from .text import router as text_router
from .fsm import router as fsm_router

__all__ = ["commands_router", "text_router", "fsm_router"]