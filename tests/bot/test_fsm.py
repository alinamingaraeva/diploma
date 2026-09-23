import pytest
from unittest.mock import AsyncMock

from bot.states import AskFlow


@pytest.mark.asyncio
async def test_ask_flow_sets_topic():
    state = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_data = AsyncMock(return_value={"topic": "hours"})

    await state.set_state(AskFlow.waiting_for_question)
    await state.update_data(topic="hours")
    state.update_data.assert_awaited()
    data = await state.get_data()
    assert data["topic"] == "hours"
    assert AskFlow.waiting_for_question.state.endswith("waiting_for_question")
