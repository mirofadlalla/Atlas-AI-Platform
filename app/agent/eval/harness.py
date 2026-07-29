"""Offline evaluation harness for agent routing and parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.utils.classification import classify_question_type
from app.agent.utils.parsing import extract_first_json_block

_GOLDEN_PATH = Path(__file__).resolve().parents[3] / "tests" / "eval" / "golden_questions.json"


def load_golden_questions(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or _GOLDEN_PATH
    with target.open(encoding="utf-8") as fh:
        return json.load(fh)


def evaluate_routing_cases(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else load_golden_questions()
    passed = 0
    failures: list[str] = []

    for case in cases:
        question = case["question"]
        expected = case["expected_type"]
        actual = classify_question_type(question)
        if actual == expected:
            passed += 1
        else:
            failures.append(f"{question!r}: expected {expected}, got {actual}")

    total = len(cases)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 1.0,
        "failures": failures,
    }


def evaluate_json_extraction(samples: list[str]) -> dict[str, Any]:
    passed = 0
    failures: list[str] = []
    for sample in samples:
        try:
            block = extract_first_json_block(sample)
            if block.startswith("{") and block.endswith("}"):
                passed += 1
            else:
                failures.append(sample[:80])
        except Exception as exc:
            failures.append(f"{sample[:40]}... ({exc})")

    total = len(samples)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 1.0,
        "failures": failures,
    }
