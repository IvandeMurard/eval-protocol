"""Case-set validation.

A case set is a specification, not a test added afterwards. Every case states,
before the model code, what "bad" means for it (`failure_trigger`): this forces
whoever adds a case to define failure in advance instead of discovering it after
the fact. One JSONL file, one case per line, so it diffs cleanly in review.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("id", "category", "input", "failure_trigger")


def validate(path: str | Path) -> list[str]:
    """Return a list of problems; an empty list means the case set is well formed."""
    p = Path(path)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]

    errors: list[str] = []
    seen: set[str] = set()
    cases = 0
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(case, dict):
            errors.append(f"line {number}: a case must be a JSON object")
            continue
        cases += 1
        for key in REQUIRED:
            value = case.get(key)
            if value in (None, "", [], {}):
                errors.append(f"line {number}: missing or empty '{key}'")
        if "expected" not in case and "accept" not in case:
            errors.append(f"line {number}: needs 'expected' or 'accept' (the answer you already know)")
        case_id = str(case.get("id", ""))
        if case_id in seen:
            errors.append(f"line {number}: duplicate id '{case_id}'")
        seen.add(case_id)

    if cases == 0 and not errors:
        errors.append("the case set is empty")
    return errors
