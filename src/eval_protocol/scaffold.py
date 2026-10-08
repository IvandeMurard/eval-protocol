"""`eval-protocol init`: the files a team needs before the first line of model code."""
from __future__ import annotations

from pathlib import Path

PROTOCOL_JSON = """{
  "max_regression_pp": 3,
  "canary_runs": 3,
  "tiers": [
    {
      "tier": 1,
      "name": "safety",
      "threshold": 1.0,
      "graders": [],
      "rationale": "WRITE THIS FIRST. The failures that cause real harm. No budget. Put the graders that guard them here."
    },
    {
      "tier": 2,
      "name": "trust",
      "threshold": 0.95,
      "graders": [],
      "rationale": "Usable when degraded, but erodes the reason to trust the system."
    },
    {
      "tier": 3,
      "name": "form",
      "threshold": 0.90,
      "graders": [],
      "rationale": "Wording and discipline. A miss misleads nobody about a limit. Graders no tier claims land here."
    }
  ]
}
"""

# One placeholder case, so `validate-dataset` has something to read and the shape is visible.
CASES_JSONL = (
    '{"id": "example-01", "category": "edge", "input": "REPLACE: a situation whose correct answer you already know", '
    '"expected": "REPLACE: that answer", '
    '"failure_trigger": "REPLACE: the sentence that states what would make this case fail"}\n'
)

GATE_YML = """# Template: adapt the two commands marked TODO to your harness.
# The harness writes eval/results.json; eval-protocol turns it into the verdict.
# Exit 0 PASS, 3 WARN (does not block), 1 FAIL and 2 ERROR block the merge.
name: eval-gate
on:
  pull_request:
  workflow_dispatch:
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install git+https://github.com/IvandeMurard/eval-protocol
      - run: eval-protocol validate-dataset eval/cases.jsonl
      # TODO: run your offline harness here (no API key, no cost) and write eval/results.json
      - run: echo "run the offline harness"
      - id: verdict
        run: |
          set +e
          eval-protocol verdict eval/results.json \\
            --protocol eval/protocol.json --baseline eval/baselines/offline.json --md verdict.md
          code=$?
          [ "$code" -eq 3 ] && code=0   # WARN is reported, not blocking
          exit $code
      - if: always()
        run: cat verdict.md >> "$GITHUB_STEP_SUMMARY"
# A live target costs tokens. Keep it behind a label or a manual trigger so CI
# cannot spend on its own initiative.
"""

TRIGGERS_JSON = """{
  "layers": ["model"],
  "triggers": [
    {"paths": ["REPLACE/model/code/*"], "layers": ["model"]},
    {"paths": ["prompts/*", "eval/cases.jsonl"], "layers": "all"}
  ],
  "exempt_label": "eval-exempt"
}
"""

FILES = {
    "eval/protocol.json": PROTOCOL_JSON,
    "eval/triggers.json": TRIGGERS_JSON,
    "eval/cases.jsonl": CASES_JSONL,
    "eval/baselines/.gitkeep": "",
    ".github/workflows/eval-gate.yml": GATE_YML,
}


def scaffold(root: Path) -> tuple[list[Path], list[Path]]:
    created: list[Path] = []
    skipped: list[Path] = []
    for rel, content in FILES.items():
        target = root / rel
        if target.exists():
            skipped.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created.append(target)
    return created, skipped
