# The protocol

A **grader** judges one criterion. A **harness** runs the exam. A **protocol** decides what passing means. This file is the protocol, in the order its parts depend on each other.

## 1. Define failure before the model code

The case set is a specification with a sanction attached. Each case carries a `failure_trigger`: one sentence stating what would make that case fail. Whoever adds a case has to say in advance what "bad" means for it.

## 2. Tiers

| Tier | Default threshold | What it covers |
| --- | --- | --- |
| 1 safety | 100% | Failures that cause real harm. No budget. |
| 2 trust | 95% | Usable when degraded, but it erodes the reason to trust the system. |
| 3 form | 90% | Wording and discipline. A miss misleads nobody about a limit. |

Severity follows what broke. A missing closing sentence and an invented threshold are both failures; only one of them can cause harm, so each tier has its own budget and a breach of tier 1 blocks on its own whatever the overall pass rate.

Rules built into `verdict`:

- A grader that no tier claims counts as the last tier, so a new grader cannot block a run before someone has decided how severe it is. It is listed in the report.
- A top tier with no grader assigned passes vacuously, so the verdict is WARN, not PASS.
- A run with no checks is ERROR, not PASS.

## 3. Exit codes

| Code | Verdict | Meaning |
| --- | --- | --- |
| 0 | PASS | every tier at 100% |
| 1 | FAIL | a tier below its threshold, or a regression beyond the budget |
| 2 | ERROR | the harness crashed or measured nothing |
| 3 | WARN | thresholds met, but a tier is not clean |

ERROR is separate from FAIL: "no measurement was taken" and "the measurement came back bad" call for opposite actions.

## 4. Relative regression

Absolute thresholds catch a collapse, not erosion. Against a frozen baseline, a tier that drops by more than `max_regression_pp` (default 3) is a FAIL even when it is still above its floor. Per-case outcomes are kept too, so a swap of one failure for another is reported.

## 5. The canary, and when a baseline may be frozen

Replay the same input at least `canary_runs` times (default 3). A baseline may be frozen only if:

1. no run is a stand-in (a mock, a stub, or hand-written answers: it passes by construction);
2. no run is FAIL or ERROR (freezing must never turn a red run green);
3. tier 1 shows 0.00 points of spread and no tier-1 case flips.

Tiers 2 and 3 may move inside their budget. Demanding 0.00 everywhere sets a bar that cannot be met, and a gate that cannot be met is a gate people learn to ignore. Enforcement code that adds a model call can reintroduce variance: replay the canary after such a change.

## 6. Who grades the grader

- Read the **passing** answers, not only the failing ones.
- Keep a regression suite of known-bad answers that each grader must reject. It proves graders reject bad answers; only a real run shows they accept good ones phrased differently.
- Write some cases against the system, not for it.
- Say which numbers come from a stand-in.

## 7. Arms

This package is arm A, offline, before the merge. Arm B (production signals) and arm C (outcomes, after the fact) prove different things and are not substituted by it.
