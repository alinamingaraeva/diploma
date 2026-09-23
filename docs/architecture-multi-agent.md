# Мультиагент researcher → writer (ДЗ 6.5)

Сначала пробовали `langgraph_supervisor.create_supervisor`: на Polza handoff-tools дают 502 «некорректный вызов инструмента». Рабочий вариант — ручной граф `Command(goto=...)`: START → researcher → writer → END. InMemorySaver, thread_id префикс `exp-langgraph`.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	researcher(researcher)
	writer(writer)
	__end__([<p>__end__</p>]):::last
	__start__ --> researcher;
	researcher --> writer;
	writer --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
