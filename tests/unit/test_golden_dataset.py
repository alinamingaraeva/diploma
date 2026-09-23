from pathlib import Path
import json


def test_golden_dataset_has_at_least_30_pairs():
    payload = json.loads(Path("tests/eval/golden_dataset.json").read_text(encoding="utf-8"))
    assert len(payload) >= 30
    for row in payload:
        assert row["user_input"].strip()
        assert row["reference"].strip()
        assert row["reference_contexts"]
