from app.services.agent_react import SYSTEM, TOOLS, run_react_with_reflection


def test_system_delegates_send_confirmation_to_graph():
    assert "обязательно вызови send_telegram_message" in SYSTEM
    assert "граф сам остановит действие" in SYSTEM


def test_react_rejects_huge_iteration_cap():
    try:
        run_react_with_reflection("x", max_iterations=30)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_react_tools_are_strict():
    for item in TOOLS:
        schema = item["function"]["parameters"]
        assert schema.get("additionalProperties") is False
