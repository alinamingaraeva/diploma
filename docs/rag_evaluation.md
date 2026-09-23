# Оценка RAG (ДЗ 5.6)

Числа ниже скопированы из `tests/eval/results/*.json` после `python scripts/run_eval.py`.

## 1. Конфигурация

| Параметр | Значение |
|----------|----------|
| Production LLM | `openai/gpt-4o-mini` (Polza) |
| Judge LLM | `openai/gpt-4o-mini` (Polza) — Anthropic/Claude в проекте нет |
| Embeddings | `openai/text-embedding-3-small`, dim 1536, COSINE |
| Chunking (baseline 5.4) | fixed, size **512**, overlap 64 |
| Chunking (финал 5.6) | fixed, size **1024**, overlap 64 |
| Retrieve K / top_n | **24** / **5** |
| Re-ranker | `BAAI/bge-reranker-v2-m3`, **выключен** |
| Score-guard | 0.38 |
| Коллекция baseline / B | `rag_assistant` (чанки 512) |
| Коллекция эксперимента A и прода | `rag_eval_1024` (чанки 1024) |
| Дедуп | один stem на файл (md/html/pdf/docx + hash-префикс PDF) |
| Генерация | полный текст чанка до 1500 символов, не snippet 300 |

Пять метрик в каждом прогоне: Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall (`ragas.metrics.collections`) и `has_citation` (`@discrete_metric`). Судья и эмбеддинги судьи — через `llm_factory` / `embedding_factory` на Polza.

## 2. Golden dataset

- Сырой прогон генератора: `tests/eval/golden_dataset_raw.csv` (`python scripts/generate_testset.py`). TestsetGenerator RAGAS упал без `rapidfuzz`, после установки сработал fallback LLM — 36 сырых строк.
- Ручная вычитка: `tests/eval/golden_dataset.json` — **32** пары `user_input` / `reference` / `reference_contexts`.
- Выкинуты слишком общие («что такое музей»), offtopic/ЧМ-2018 (ломают `has_citation` на refusal) и дубли телефонов.
- Вопросы покрывают контакты, часы, билеты, правила, экскурсии, площадки, как добраться.

## 3. Baseline

Конфиг ДЗ 5.4 после правок retrieval/generation (дедуп форматов, полный чанк, `RAG_RETRIEVE_K=24`): chunk 512, top_n=5, rerank off, коллекция `rag_assistant`.

Артефакт: `tests/eval/results/2026-08-28_1515_baseline.csv`

| Метрика | Mean |
|---------|------|
| faithfulness | 0.887 |
| answer_relevancy | 0.668 |
| context_precision | 0.834 |
| context_recall | 1.000 |
| has_citation | 0.906 |
| latency_ms | 3154 |

Пороги чекпоинта на baseline **не** закрыты: relevancy 0.668 < 0.7, citation 0.906 < 0.95. Три отказа на фактах из базы (билет естественной истории, зимний выходной, Тайницкая башня) — в top-5 после дедупа попадал «хвост» 512-чанка без нужных строк.

Ранние CSV `1430` / `1443` / `1458` — audit log до фикса дедупа и промпта; в таблицы A/B не входят.

## 4. Эксперимент A: chunk_size 512 → 1024

Один параметр: размер чанка. Overlap 64, top_n=5, retrieve_k=24, rerank off. Индекс: `rag_eval_1024` (`python scripts/ingest.py data/` с `RAG_CHUNK_SIZE=1024`).

Артефакт: `tests/eval/results/2026-08-28_1532_chunk_1024.csv`

| Вариант | faithfulness | answer_relevancy | context_precision | context_recall | has_citation | latency_ms |
|---------|-------------:|-----------------:|------------------:|---------------:|-------------:|-----------:|
| baseline 512 | 0.887 | 0.668 | 0.834 | 1.000 | 0.906 | 3154 |
| chunk 1024 | **0.938** | **0.749** | **0.893** | 1.000 | **1.000** | 3256 |

Короткий музейный файл (tickets/hours/contacts) целиком помещается в один чанк 1024: LLM видит цену 450 ₽ и зимние часы Тайницкой, а не обрубок соседнего абзаца. Пороги чекпоинта закрыты. Latency +100 мс — приемлемо.

## 5. Эксперимент B: top_n 5 → 10

Один параметр: сколько уникальных чанков отдаём в генерацию. Коллекция та же, что baseline (`rag_assistant`, 512), retrieve_k=24.

Артефакт: `tests/eval/results/2026-08-31_0832_top_k_10.csv`

| Вариант | faithfulness | answer_relevancy | context_precision | context_recall | has_citation | latency_ms |
|---------|-------------:|-----------------:|------------------:|---------------:|-------------:|-----------:|
| baseline top_n=5 | 0.887 | 0.668 | 0.834 | 1.000 | 0.906 | 3154 |
| top_n=10 | 0.870 | **0.732** | 0.820 | 1.000 | 0.938 | 3513 |

Relevancy выросла, но faithfulness и precision просели (шум чужих площадок в промпте), citation 0.938 < 0.95, latency выше. Больше контекста на 512-чанках не лечит обрезку факта внутри одного файла.

## 6. Финальный конфиг

Беру вариант **chunk_1024**, потому что на том же golden из 32 вопросов он единственный закрывает пороги (faithfulness 0.94 > 0.7, answer_relevancy 0.75 > 0.7, has_citation 1.0 > 0.95) и лучше baseline по precision; top_n=10 эти пороги не берёт и добавляет ~350 мс.

Зафиксировано в `app/core/config.py`, `.env` и `.env.example`:

| Параметр | Финал |
|----------|--------|
| LLM | `openai/gpt-4o-mini` |
| Embedding | `openai/text-embedding-3-small`, 1536, COSINE |
| `RAG_CHUNK_STRATEGY` | `fixed` |
| `RAG_CHUNK_SIZE` | `1024` |
| `RAG_CHUNK_OVERLAP` | `64` |
| `RAG_RETRIEVE_K` | `24` |
| `RAG_SIMILARITY_TOP_K` | `5` |
| `RAG_RERANK_ENABLED` | `false` |
| `RAG_COLLECTION` | `rag_eval_1024` |
| `RAG_DOCSTORE_PATH` | `./var/ingestion/docstore_1024.json` |
| `RAG_SCORE_THRESHOLD` | `0.38` |

Это тот же индекс, что в CSV `2026-08-28_1532_chunk_1024`.

## 7. Failure analysis

Топ худших по faithfulness из финального CSV `2026-08-28_1532_chunk_1024.csv`. У всех трёх `context_recall = 1.0`: ретривер нужный фрагмент принёс.

### 1. «Сколько стоит взрослый билет в Музей естественной истории?»

| Поле | Значение |
|------|----------|
| faithfulness / relevancy / citation | 0.00 / 0.76 / 1.00 |
| response | «Взрослый билет … стоит 450 ₽ [1].» |
| retrieved | `tickets.*`: «Музей естественной истории … взрослые: 450 ₽» |
| диагноз | **generation/judge**: низкий faith + высокий recall. Ответ дословно из контекста; судья gpt-4o-mini поставил 0 — шум RAGAS, не баг ретривера. |

### 2. «До скольких работают кассы в Спасской башне и визит-центре?»

| Поле | Значение |
|------|----------|
| faithfulness / relevancy / citation | 0.50 / 0.93 / 1.00 |
| response | «Кассы … ежедневно с 8:00 до 20:00 [1].» |
| retrieved | hours: «Кассы в Спасской башне, Тайницкой башне и Визит-центре: ежедневно 8:00–20:00» |
| диагноз | **generation/judge**. Факт в контексте, ответ верный; половинный faith — снова шум судьи. |

### 3. «Где купить билет в музеи Казанского Кремля?»

| Поле | Значение |
|------|----------|
| faithfulness / relevancy / citation | 0.67 / 0.97 / 1.00 |
| response | официальная касса `tickets.kazan-kremlin.ru` + Пушкинская карта [1] |
| retrieved | тот же `tickets.*` |
| диагноз | **generation/judge**. Ретривер в порядке; судья занизил faith на полностью обоснованном ответе. |

### 4. «Чем часы работы музеев в пятницу отличаются от понедельника–четверга?»

| Поле | Значение |
|------|----------|
| faithfulness / relevancy / citation | 0.83 / 0.88 / 1.00 |
| response | пт 11:00–20:00 vs пн–чт 10:00–18:00 [1] |
| retrieved | полный `hours.*` (чанк 1024) |
| диагноз | лёгкий **generation**: опечатка «истории государственной» вместо «государственности»; часы верные. |

Матрица 2×2 на финальном прогоне: retriever-проблем (низкий faith + низкий recall) нет. Оставшиеся просадки — judge noise и мелкие оговорки генерации.

## 8. Известные проблемы и план

- RAGAS — LLM-as-judge, шум **±5–10%**. На 32 вопросах сравнение A/B осмысленно; historic baseline с другим судьёй невалиден.
- Судья тот же `gpt-4o-mini`, что и генератор: дешевле и доступен через Polza, слабее claude-sonnet. Пример: верные 450 ₽ получили faithfulness 0.0.
- Корпус продублирован в md/html/pdf/docx. Без дедупа по stem top-5 заполнялся пятью копиями `contacts.*`. Лечится `_unique_by_file` + `RAG_RETRIEVE_K=24`.
- Anthropic в `.env` нет — в `pyproject.toml` extra `eval` пакет `anthropic` не ставим.
- Phoenix HallucinationEvaluator не запускали (опциональный +30 мин). 2026-08-31: `python scripts/trace_phoenix.py` отправил **22** запроса, проект `diploma-fastapi`, UI http://localhost:6006. В проекте есть spans `RETRIEVER` (`VectorIndexRetriever.retrieve`), `LLM` (`ChatCompletion`) и `EMBEDDING`. Shim `llama_index.core.base.agent.types` нужен из‑за LlamaIndex 0.14.24.
- План: сменить судью на более сильную модель при появлении ключа; не смешивать 512- и 1024-индексы в одной коллекции; при росте корпуса вернуть rerank только после замера latency.

Порог чекпоинта 0.7 для музейной справки считаем достаточным (не мед/юр/фин). Финальный прогон его проходит.
