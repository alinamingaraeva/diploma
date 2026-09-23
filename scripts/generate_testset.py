"""Генерация сырого golden через RAGAS TestsetGenerator, затем ручная вычитка в JSON."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.eval.metrics import make_async_openai
from app.services.llama_setup import configure_llama
from app.services.rag_common import make_sync_http_client

OUT_RAW = ROOT / "tests" / "eval" / "golden_dataset_raw.csv"
MUSEUM = ROOT / "data" / "museum"


def _rows_from_testset(testset) -> list[dict]:
    rows = []
    to_pandas = getattr(testset, "to_pandas", None)
    if callable(to_pandas):
        frame = to_pandas()
        for record in frame.to_dict(orient="records"):
            rows.append(
                {
                    "user_input": record.get("user_input") or record.get("question") or "",
                    "reference": record.get("reference") or record.get("ground_truth") or "",
                    "reference_contexts": record.get("reference_contexts")
                    or record.get("contexts")
                    or [],
                }
            )
        return rows
    samples = getattr(testset, "samples", None) or list(testset)
    for sample in samples:
        rows.append(
            {
                "user_input": getattr(sample, "user_input", "") or getattr(sample, "question", ""),
                "reference": getattr(sample, "reference", "") or "",
                "reference_contexts": getattr(sample, "reference_contexts", None) or [],
            }
        )
    return rows


def _fallback_llm_pairs(settings) -> list[dict]:
    from openai import OpenAI

    http = make_sync_http_client(settings)
    llm = OpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http,
        timeout=60.0,
    )
    rows = []
    for path in sorted(MUSEUM.glob("*.md")):
        if path.stem == "offtopic":
            continue
        text = path.read_text(encoding="utf-8")[:3500]
        completion = llm.chat.completions.create(
            model=settings.eval_judge_model,
            messages=[
                {
                    "role": "system",
                    "content": "По документу музея сформулируй 2 конкретных вопроса посетителя и краткие эталонные ответы. "
                    "JSON-массив объектов {user_input, reference}. Только факты из текста, на русском.",
                },
                {"role": "user", "content": text},
            ],
        )
        raw = completion.choices[0].message.content or "[]"
        start, end = raw.find("["), raw.rfind("]")
        if start < 0 or end < 0:
            continue
        try:
            items = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            continue
        for item in items:
            question = (item.get("user_input") or "").strip()
            reference = (item.get("reference") or "").strip()
            if question and reference:
                rows.append(
                    {
                        "user_input": question,
                        "reference": reference,
                        "reference_contexts": [text[:800]],
                    }
                )
    http.close()
    return rows


def main() -> None:
    settings = get_settings()
    OUT_RAW.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    try:
        from llama_index.core import SimpleDirectoryReader
        from ragas.llms import llm_factory
        from ragas.testset import TestsetGenerator

        http = make_sync_http_client(settings)
        configure_llama(settings, http)
        docs = SimpleDirectoryReader(str(MUSEUM), required_exts=[".md"]).load_data()
        client = make_async_openai(settings)
        generator_llm = llm_factory(settings.eval_judge_model, client=client)
        try:
            from ragas.embeddings.base import embedding_factory

            embeddings = embedding_factory("openai", model=settings.eval_embed_model, client=client)
        except Exception:
            embeddings = None
        generator = TestsetGenerator(llm=generator_llm, embedding_model=embeddings)
        testset = generator.generate_with_llamaindex_docs(docs, testset_size=32)
        rows = _rows_from_testset(testset)
        http.close()
    except Exception as exc:
        print(f"TestsetGenerator недоступен или упал ({exc!r}), fallback на LLM по файлам")
        rows = _fallback_llm_pairs(settings)
    if not rows:
        raise SystemExit("Не удалось сгенерировать ни одной пары")
    with OUT_RAW.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user_input", "reference", "reference_contexts"])
        writer.writeheader()
        for row in rows:
            contexts = row.get("reference_contexts") or []
            if isinstance(contexts, list):
                contexts = " | ".join(str(item) for item in contexts)
            writer.writerow(
                {
                    "user_input": row.get("user_input", ""),
                    "reference": row.get("reference", ""),
                    "reference_contexts": contexts,
                }
            )
    print(f"wrote {len(rows)} rows -> {OUT_RAW}")
    print("Дальше: вычитать вручную в tests/eval/golden_dataset.json (уже есть проверенный набор).")


if __name__ == "__main__":
    main()
