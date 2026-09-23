from app.services.agent_react import TOOLS, run_react_with_reflection


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
