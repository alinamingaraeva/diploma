import json
import logging
from typing import Any

from openai import AsyncOpenAI
from structlog import get_logger

from app.prompts.loader import render_system_prompt
from app.tools.handlers import execute_tool
from app.tools.schemas import OPENAI_TOOLS

logger = get_logger(__name__)
stdlib_logger = logging.getLogger("tool_call")


class ToolCallingClient:
    """Полный цикл function calling: tools → tool_calls → handler → финальный ответ."""

    def __init__(self, openai_client: AsyncOpenAI, model: str):
        self.openai = openai_client
        self.model = model

    async def complete(
        self,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
        canary: str = "",
    ) -> dict[str, Any]:
        system = render_system_prompt(canary=canary)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        logger.info("tool_loop.input", input=user_input)
        stdlib_logger.info("input=%s", user_input)

        first = await self.openai.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=OPENAI_TOOLS,
            temperature=0.2,
        )
        usage_total = (first.usage.total_tokens if first.usage else 0) or 0
        choice = first.choices[0]
        tool_calls = choice.message.tool_calls or []

        if not tool_calls:
            text = choice.message.content or ""
            logger.info(
                "tool_loop.no_tool",
                final_answer=text[:300],
                tokens=usage_total,
            )
            return {
                "text": text,
                "used_tool": False,
                "tool_name": None,
                "tool_args": None,
                "tool_result": None,
                "tokens": usage_total,
            }

        assistant_msg = choice.message.model_dump()
        messages.append(assistant_msg)

        first_call = tool_calls[0]
        name = first_call.function.name
        try:
            args = json.loads(first_call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        result = execute_tool(name, args)
        logger.info("tool_loop.call", tool=name, args=args, result=result[:500], tokens=usage_total)
        stdlib_logger.info("tool=%s args=%s result=%s", name, args, result[:300])

        for call in tool_calls:
            call_name = call.function.name
            try:
                call_args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                call_args = {}
            call_result = execute_tool(call_name, call_args) if call.id != first_call.id else result
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": call_result,
                }
            )

        second = await self.openai.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
        )
        if second.usage:
            usage_total += second.usage.total_tokens or 0
        final = second.choices[0].message.content or ""
        logger.info("tool_loop.final", final_answer=final[:300], tokens=usage_total)
        return {
            "text": final,
            "used_tool": True,
            "tool_name": name,
            "tool_args": args,
            "tool_result": result,
            "tokens": usage_total,
        }
