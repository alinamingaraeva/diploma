from functools import lru_cache
from pathlib import Path

from jinja2 import Template

PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=16)
def render_system_prompt(version: str = "v1", **context) -> str:
    text = (PROMPTS_DIR / f"system_{version}.j2").read_text(encoding="utf-8")
    return Template(text).render(**context)


def load_tool_description(name: str) -> str:
    path = PROMPTS_DIR / "tools" / f"{name}.md"
    return path.read_text(encoding="utf-8").strip()
