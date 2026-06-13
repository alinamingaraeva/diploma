from typing import List, Dict

# Модели OpenAI с ценами за 1K токенов (пример)
MODELS_LIST: List[Dict] = [
    {"id": "gpt-4o-mini", "name": "GPT-4o mini", "context_length": 128000, "pricing": {"input": 0.00015, "output": 0.0006}},
    {"id": "gpt-4o", "name": "GPT-4o", "context_length": 128000, "pricing": {"input": 0.005, "output": 0.015}},
    {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "context_length": 16385, "pricing": {"input": 0.001, "output": 0.002}},
]

def get_models():
    return MODELS_LIST