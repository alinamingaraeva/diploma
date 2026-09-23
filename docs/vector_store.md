# Векторное хранилище (ДЗ 5.2)

Коллекция `documents` в Qdrant: **106** чанков из `data/museum/`, размерность **1536** (`openai/text-embedding-3-small` через Polza). Payload: `source`, `text`, `created_at`, `category`. Индексы: `source` KEYWORD, `created_at` DATETIME, `category` KEYWORD.

Поднять: `docker compose up -d qdrant` → дашборд [http://localhost:6333/dashboard](http://localhost:6333/dashboard). URL, ключ, имя коллекции и `EMBEDDING_DIM` читаются из `.env`, в `vector_store.py` не хардкодятся.

Загрузка:

```bash
python scripts/load_to_qdrant.py
python scripts/load_to_qdrant.py --compare
```

Первый прогон: `points_count=106 dim=1536`. Повторный — тоже **106** (идемпотентный `uuid5` по `source:chunk_index`). Временные `documents_cosine` / `documents_dot` после сравнения удаляются.

## HNSW

В `ensure_collection` явно: `HnswConfigDiff(m=16, ef_construct=100)`. Это дефолт Qdrant; для корпуса музея (<100k точек) больше `m` не даёт выигрыша, только раздувает граф. `ef` на запросе оставляем серверный default.

Клиент создаётся один раз в `VectorStore` и живёт в `app.state` (lifespan FastAPI вызывает `ensure_collection`). Поиск — `query_points`, не deprecated `search`.

## Метрика: cosine vs dot

Одни и те же 106 векторов залиты в `documents_cosine` (`Distance.COSINE`) и `documents_dot` (`Distance.DOT`). Пять реальных вопросов посетителя, top-5 id.

| Запрос | top-5 COSINE | top-5 DOT | Совпало |
|--------|----------------|-----------|---------|
| Телефон визит-центра Казанского Кремля | `adeb3cf5-edc4-540b-b63c-6c4116e7bcff`<br>`e2b69ab6-fb72-5cf2-b0e5-bf9a55f0ac3b`<br>`9ac0eb11-f45f-5826-aacb-9cbfc5a5f565`<br>`5b078b94-70b0-5e77-8bc5-2567a9bcf950`<br>`0a0bf9e7-7b4d-5380-b841-bb75dc6dbf27` | те же id, тот же порядок | да |
| Часы работы музея естественной истории в пятницу | `33792a8e-7041-55a4-98b2-534b612498c4`<br>`2a25f115-9ca8-53e7-8c1c-81be7b3adc62`<br>`836111e3-d6de-52c3-b00c-a5c393dffdf8`<br>`eba409e4-2871-51ac-9b45-1dc84f827009`<br>`f6e84a45-8697-5dbf-bfcd-3a8195baac5b` | те же id, тот же порядок | да |
| Где купить билет в Эрмитаж-Казань | `97dd7727-f1a6-595f-b193-bd8cae948944`<br>`1ea9236e-8f23-5e82-b5b9-a541d2f6b35d`<br>`1cab7602-2915-5656-b580-4660b0287ca8`<br>`97a19d06-ab96-58ff-9955-92273abc9a59`<br>`3028ee15-de0d-5398-afa9-85978209d364` | те же id, тот же порядок | да |
| Можно ли зайти в Кремль с собакой | `eb0c3ae2-6d1e-5bc2-823f-89510227ec49`<br>`67132e51-8b5c-5d0d-950e-37e28b8bedfd`<br>`b4fab545-38db-5f97-b501-bf59f90537e1`<br>`25b28624-31d7-5d23-94ba-d8a5b968c29e`<br>`78d74312-2140-5855-a352-2c7996a96e0b` | те же id, тот же порядок | да |
| Экскурсия в мечеть Кул-Шариф в пятницу | `058ac113-58c5-541c-9a0a-05a526c191a6`<br>`8a5a337a-ffb8-5a71-8bf2-b6b886d51c5a`<br>`95541170-a95b-570e-9669-3ab837bdd04e`<br>`f6e84a45-8697-5dbf-bfcd-3a8195baac5b`<br>`82f94fe1-2d23-5caa-bbe6-4239904e9711` | те же id, тот же порядок | да |

Ранжирование совпало на всех пяти запросах — ожидаемо: `text-embedding-3-small` отдаёт **нормализованные** векторы, для них cosine и dot product дают один порядок. В production оставляем **COSINE**: score в диапазоне примерно \([-1, 1]\) читается как сходство, это default Qdrant и то, что потом ждёт LlamaIndex на 5.3.

## Фильтры

Запросы ниже — против боевой коллекции `documents`.

### 1. Match по `category`

Запрос: «часы работы музеев».

```python
from qdrant_client.models import FieldCondition, Filter, MatchValue

query_filter = Filter(
    must=[FieldCondition(key="category", match=MatchValue(value="hours"))]
)
```

Top-3:

| source | score | фрагмент |
|--------|-------|----------|
| `hours.md` | 0.564 | молитвы с 11:30 до 13:15. Благовещенский собор открыт ежедневно с 8:00 до 20:00 |
| `hours.md` | 0.524 | залы Присутственных мест, Музей Спасской башни: пн–чт 10:00–18:00 |
| `hours.md` | 0.508 | # Режим работы музея-заповедника «Казанский Кремль» |

Без этого фильтра в топ попадали бы смешанные категории (`natural_history.md`, `manezh.md`). С `category=hours` — только страница режима работы.

### 2. Range по `created_at`

`offtopic.md` датирован **2024-01-15** (намеренно старый шум). Остальной корпус — свежий.

Запрос: «рецепт чак-чака и погода в Сочи».

```python
from datetime import datetime, timedelta, timezone
from qdrant_client.models import DatetimeRange, FieldCondition, Filter

since = datetime.now(timezone.utc) - timedelta(days=30)
query_filter = Filter(
    must=[FieldCondition(key="created_at", range=DatetimeRange(gte=since))]
)
```

Без фильтра (старый документ в топе):

| source | score | фрагмент |
|--------|-------|----------|
| `offtopic.md` | 0.658 | специально не про Казанский Кремль … рецепт чак-чака |
| `offtopic.md` | 0.578 | яйца, мёд и масло. Погода в Сочи в августе |
| `events.md` | 0.337 | кинопоказы под открытым небом |

С фильтром «последние 30 дней» `offtopic.md` пропадает, в топе свежие страницы:

| source | score | фрагмент |
|--------|-------|----------|
| `events.md` | 0.337 | кинопоказы под открытым небом |
| `excursions.md` | 0.296 | экскурсии по музеям … Пушкинская карта |
| `hermitage_kazan.md` | 0.295 | Режим работы: пн–чт 10:00–18:00 |

### 3. Композитный `must` + `must_not`

Запрос: «экспозиция музея естественной истории». Аналог production-паттерна «только нужный тип документа, без архива/мусора».

```python
from qdrant_client.models import FieldCondition, Filter, MatchValue

query_filter = Filter(
    must=[FieldCondition(key="category", match=MatchValue(value="museums"))],
    must_not=[FieldCondition(key="source", match=MatchValue(value="offtopic.md"))],
)
```

Top-3:

| source | score | фрагмент |
|--------|-------|----------|
| `natural_history.md` | 0.551 | # Музей естественной истории Республики Татарстан |
| `annunciation_museum.md` | 0.454 | # Музей истории Благовещенского собора |
| `natural_history.md` | 0.449 | пн–чт 10:00–18:00; пятница 11:00–20:00 |

`offtopic.md` в выдачу не попадает даже при семантически странном запросе: категория не `museums`, плюс явный `must_not` по `source`.

## Почему не pgvector

Postgres уже есть (история чатов), но для RAG на 5.3–5.5 нужен Qdrant: hybrid/sparse, payload-фильтры без SQL, готовый `QdrantVectorStore` в LlamaIndex. Сравнивать latency на 106 точках бессмысленно. Расширение `pgvector` не подключаем.
