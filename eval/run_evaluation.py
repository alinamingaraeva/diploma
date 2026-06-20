import json
import asyncio
import httpx
import os
from datetime import datetime
from typing import List, Dict, Any
import uuid
from dotenv import load_dotenv
from openai import AsyncOpenAI   # <-- добавьте эту строку

load_dotenv()

# Настройки
JUDGE_MODEL = "gpt-4o-mini"  # или "gpt-5.2", если доступно
API_BASE = "http://localhost:8000"

async def get_answer(question: str) -> str:
    """Отправляет запрос к вашему FastAPI-сервису."""
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            f"{API_BASE}/chat",
            json={"messages": [{"role": "user", "content": question}]},
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()["content"]

async def evaluate_with_judge(question: str, answer: str, expected: str, keywords: List[str]) -> Dict[str, Any]:
    """Использует LLM как судью для оценки ответа."""
    proxy_url = "http://local_user:p32kcF26NhWE@72.56.89.38:8888"
    http_client = httpx.AsyncClient(proxy=proxy_url)
    try:
        client = AsyncOpenAI(
            api_key=os.getenv("OPENAI__API_KEY"),
            base_url=os.getenv("OPENAI__BASE_URL", "https://api.openai.com/v1"),
            http_client=http_client,
            timeout=30.0
        )
        judge_prompt = f"""
Ты — эксперт по оценке качества ответов ИИ. Оцени ответ бота по трём критериям: 
- relevance (релевантность): насколько ответ соответствует вопросу
- correctness (корректность): насколько ответ фактически верен
- completeness (полнота): насколько ответ покрывает все аспекты вопроса

Вопрос: {question}
Ожидаемый ответ (эталон): {expected}
Ключевые слова, которые должны быть отражены: {', '.join(keywords)}
Фактический ответ бота: {answer}

Сначала напиши reasoning (краткое объяснение, почему ты ставишь такие оценки), затем выставь оценки от 1 до 5 по каждому критерию.
Ответ должен быть в формате JSON:
{{
    "reasoning": "...",
    "relevance": 5,
    "correctness": 5,
    "completeness": 5
}}
"""
        response = await client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": judge_prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    finally:
        await http_client.aclose()

async def run_evaluation(golden_path: str, out_dir: str = "eval/runs"):
    """Запускает полный цикл оценки."""
    # 1. Загружаем golden dataset
    with open(golden_path, 'r', encoding='utf-8') as f:
        golden = json.load(f)
    
    items = golden["items"]
    results = []
    
    # 2. Прогоняем каждый вопрос через бота
    print(f"Запуск оценки {len(items)} вопросов...")
    for item in items:
        print(f"  Обработка {item['id']}...")
        answer = await get_answer(item["question"])
        results.append({
            "id": item["id"],
            "question": item["question"],
            "answer": answer,
            "expected": item["expected_answer"],
            "keywords": item["expected_keywords"]
        })
    
    # 3. Оцениваем каждый ответ через Judge
    print("Оценка ответов через Judge...")
    scores = []
    for res in results:
        print(f"  Оценка {res['id']}...")
        evaluation = await evaluate_with_judge(
            res["question"],
            res["answer"],
            res["expected"],
            res["keywords"]
        )
        res.update(evaluation)
        scores.append(evaluation)
    
    # 4. Агрегируем результаты
    aggregates = {
        "relevance_avg": sum(s["relevance"] for s in scores) / len(scores),
        "correctness_avg": sum(s["correctness"] for s in scores) / len(scores),
        "completeness_avg": sum(s["completeness"] for s in scores) / len(scores),
        "min_correctness": min(s["correctness"] for s in scores),
    }
    
    # 5. Сохраняем результат
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "model_under_test": "gpt-4o-mini",
        "judge_model": JUDGE_MODEL,
        "golden_version": golden.get("version", 1),
        "items": results,
        "aggregates": aggregates
    }
    
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{datetime.now().strftime('%Y-%m-%d')}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Результаты сохранены в {out_path}")
    print(f"📊 Средняя корректность: {aggregates['correctness_avg']:.2f}")

if __name__ == "__main__":
    asyncio.run(run_evaluation("eval/golden_dataset.json"))