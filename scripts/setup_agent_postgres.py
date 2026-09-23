"""Один раз создаёт таблицы LangGraph checkpointer в том же Postgres, что и чат."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import get_settings
from app.services.agent_persistent import postgres_dsn


def main() -> None:
    settings = get_settings()
    dsn = postgres_dsn(settings.database_url)
    host = dsn.split("@")[-1]
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()
    print("checkpoint tables ready at", host)


if __name__ == "__main__":
    main()
