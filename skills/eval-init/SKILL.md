---
name: eval-init
description: Set up evaluation for an LLM agent before writing more model code - a case set with known answers, severity tiers with budgets, a blocking CI gate. Use when the user is starting an agent, asks how to know it works or has stopped working, wants an eval gate, or ships an agent with no acceptance criteria.
---

# eval-init: define "working" before the model code

Evaluation is a contract written first, with a sanction attached. Do these in order; do not skip ahead to graders.

## 1. Check the tool is available

```bash
eval-protocol --help || pip install git+https://github.com/IvandeMurard/eval-protocol
```

## 2. Scaffold

```bash
eval-protocol init .
```

This creates `eval/protocol.json`, `eval/cases.jsonl`, `eval/baselines/` and a CI template. It never overwrites an existing file.

## 3. Interview the user, then fill in the files

Ask, one topic at a time, and write the answers into the files rather than inventing them:

1. **What is a bad output?** Ask for the worst thing the agent could say or do. That defines **tier 1** (threshold 1.0, no budget). Typical members: an invented figure, a refusal followed by a guess, contradicting the source of truth, inventing agreement. Name the grader for each in `eval/protocol.json`.
2. **What erodes trust without causing harm?** That is tier 2 (default 0.95). **What is only form?** That is tier 3 (default 0.90).
3. **Cases.** Each line of `eval/cases.jsonl` needs `id`, `category`, `input`, `expected` (or `accept`), and `failure_trigger`: one sentence stating what would make *this* case fail. Ask for cases the user already knows the answer to, including the awkward ones (boundaries, two sources that disagree, social pressure). Never write the expected answers yourself from your own assumptions about the domain.

Run `eval-protocol validate-dataset eval/cases.jsonl` after each batch.

## 4. Graders

Prefer pure functions (no model deciding) for anything in tier 1. A grader that needs a model to decide fails in the same way as the thing it grades. If an LLM judge is unavoidable, it must be calibrated against human verdicts before it is allowed to block, and it never gates tier 1 alone.

The harness must write `eval/results.json`: `{"target": "...", "temperature": 0, "stand_in": false, "checks": [{"case_id": "...", "grader": "...", "passed": true}]}`. Set `"stand_in": true` whenever the run grades a mock, a stub or hand-written answers: that run may gate a pipeline but can never become a baseline.

## 5. Gate

```bash
eval-protocol verdict eval/results.json --protocol eval/protocol.json
```

Exit 0 PASS, 1 FAIL, 2 ERROR (nothing was measured), 3 WARN (within budget but not clean; read it, do not ignore it). A tier with no grader assigned reports WARN: a safety tier that checks nothing is not a clean pass.

Do **not** freeze a baseline yet. Use `eval-canary` first.

## Say plainly what is not covered

At the end, state which of the three arms exist: offline (before the merge), runtime (production signals), outcome (did reality prove it right). Most first setups are arm A only. Say so.
