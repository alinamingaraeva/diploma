"""Сохраняет mermaid-схемы custom и prebuilt графов (ДЗ 6.3)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_graph import custom_graph, prebuilt_graph

DOCS = ROOT / "docs"


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    custom_mmd = custom_graph.get_graph().draw_mermaid()
    prebuilt_mmd = prebuilt_graph.get_graph().draw_mermaid()
    (DOCS / "agent-graph-custom.mmd").write_text(custom_mmd, encoding="utf-8")
    (DOCS / "agent-graph-prebuilt.mmd").write_text(prebuilt_mmd, encoding="utf-8")
    print("wrote", DOCS / "agent-graph-custom.mmd")
    print("wrote", DOCS / "agent-graph-prebuilt.mmd")
    try:
        png = custom_graph.get_graph().draw_mermaid_png()
        (DOCS / "agent-graph.png").write_bytes(png)
        print("wrote", DOCS / "agent-graph.png")
    except Exception as exc:
        print("png skipped:", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
