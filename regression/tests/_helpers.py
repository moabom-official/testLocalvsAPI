"""테스트 공통 — 골든 픽스처 로더."""
import json
import os

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "golden")


def load_text(report_kind: str, label: str) -> str:
    path = os.path.join(GOLDEN, report_kind, f"{label}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(report_kind: str, label: str):
    path = os.path.join(GOLDEN, report_kind, f"{label}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def codes(result):
    return {v.code for v in result.violations}
