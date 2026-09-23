import json

from jsonschema import Draft202012Validator

from app.tools.handlers import get_opening_hours, get_ticket_link, search_museum_info
from app.tools.schemas import OPENAI_TOOLS


def test_tool_json_schemas_are_valid():
    for tool in OPENAI_TOOLS:
        Draft202012Validator.check_schema(tool["function"]["parameters"])


def test_hours_from_file():
    data = json.loads(get_opening_hours("Кул-Шариф"))
    assert data.get("hours") or data.get("found") is False
    all_hours = json.loads(get_opening_hours())
    assert "hours" in all_hours
    assert len(all_hours["hours"]) >= 3


def test_ticket_link_real_url():
    data = json.loads(get_ticket_link("музеи"))
    assert "tickets.kazan-kremlin.ru" in data["url"]


def test_search_info():
    data = json.loads(search_museum_info("афиша"))
    assert data["results"]
