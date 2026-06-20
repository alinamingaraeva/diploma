import json
import os
import sys
import yaml
from datetime import datetime

def find_latest_run(runs_dir: str = "eval/runs") -> str:
    """Находит последний файл прогона в папке runs."""
    files = [f for f in os.listdir(runs_dir) if f.endswith('.json')]
    if not files:
        print("❌ Нет файлов прогонов в папке eval/runs/")
        sys.exit(1)
    latest = max(files, key=lambda f: os.path.getmtime(os.path.join(runs_dir, f)))
    return os.path.join(runs_dir, latest)

def check_thresholds(run_path: str, thresholds_path: str = "eval/thresholds.yaml"):
    """Проверяет агрегаты прогона на соответствие порогам."""
    # Загружаем пороги
    with open(thresholds_path, 'r', encoding='utf-8') as f:
        thresholds = yaml.safe_load(f)
    
    # Загружаем результаты прогона
    with open(run_path, 'r', encoding='utf-8') as f:
        run = json.load(f)
    
    aggregates = run.get("aggregates", {})
    errors = []
    
    for key, threshold in thresholds.items():
        value = aggregates.get(key, 0)
        if value < threshold:
            errors.append(f"  ❌ {key}: {value:.2f} < {threshold}")
    
    if errors:
        print("❌ Пороги не выполнены:")
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print("✅ Все пороги выполнены!")
        sys.exit(0)

if __name__ == "__main__":
    latest = find_latest_run()
    check_thresholds(latest)