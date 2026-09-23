from app.prompts.loader import load_tool_description

GET_OPENING_HOURS_DESCRIPTION = load_tool_description("get_opening_hours")
GET_TICKET_LINK_DESCRIPTION = load_tool_description("get_ticket_link")
SEARCH_MUSEUM_INFO_DESCRIPTION = load_tool_description("search_museum_info")

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_opening_hours",
            "description": GET_OPENING_HOURS_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "museum": {
                        "type": "string",
                        "description": "Название площадки (музей, касса, собор, мечеть). Пусто — все площадки.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ticket_link",
            "description": GET_TICKET_LINK_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "museum_or_event": {
                        "type": "string",
                        "description": "Музей или событие, для которого нужна ссылка на билет.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_museum_info",
            "description": SEARCH_MUSEUM_INFO_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос: выставка, экскурсия, правила, афиша, как добраться.",
                    }
                },
                "required": ["query"],
            },
        },
    },
]
