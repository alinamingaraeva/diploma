# Инвентаризация корпуса (ДЗ 5.5)

Источник: `data/museum/*.md` → `data/kb/<category>/` через `python scripts/download_data.py`.
Категория берётся из пути (`hours`, `museums`, `tickets`, …).

- **Файлов:** 63
- **Общий размер:** 11029153 байт (10770.7 КБ)
- **Форматы:**
  - `.docx`: 6 файлов, 226010 байт
  - `.html`: 19 файлов, 40634 байт
  - `.md`: 19 файлов, 35158 байт
  - `.pdf`: 19 файлов, 10727351 байт

Загрузка посетителем: `POST /documents/upload` кладёт файл в `data/uploads/` и индексирует фоном.

Повторный ingest: `python scripts/ingest.py data/`.
