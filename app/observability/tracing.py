import os
import sys
import types


def _shim_llama_index_agent_types() -> None:
    """openinference 3.x импортирует llama_index.core.base.agent.types, в 0.14.24 модуля нет."""
    if "llama_index.core.base.agent.types" in sys.modules:
        return
    parent_name = "llama_index.core.base.agent"
    types_name = "llama_index.core.base.agent.types"
    parent = types.ModuleType(parent_name)
    types_mod = types.ModuleType(types_name)

    class BaseAgent:  # noqa: N801
        pass

    class BaseAgentWorker:  # noqa: N801
        pass

    types_mod.BaseAgent = BaseAgent
    types_mod.BaseAgentWorker = BaseAgentWorker
    parent.types = types_mod
    sys.modules[parent_name] = parent
    sys.modules[types_name] = types_mod


def setup_tracing(project_name: str = "diploma-fastapi") -> None:
    from phoenix.otel import register
    from openinference.instrumentation.openai import OpenAIInstrumentor

    from app.core.config import get_settings

    settings = get_settings()
    if not settings.phoenix_enabled:
        print("Phoenix tracing disabled")
        return
    try:
        endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:4317")
        tracer_provider = register(
            project_name=project_name,
            endpoint=endpoint,
            protocol="grpc",
        )
        OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        try:
            _shim_llama_index_agent_types()
            from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

            LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider)
        except Exception as exc:
            print(f"LlamaIndexInstrumentor skipped: {exc!r}")
    except Exception as exc:
        print(f"Phoenix tracing skipped: {exc}")
