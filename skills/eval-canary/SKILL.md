---
name: eval-canary
description: Prove an LLM evaluation measures rather than draws, then freeze a baseline safely. Use when scores differ between identical runs, before turning an eval threshold into a blocking gate, before freezing or re-freezing a baseline, or when a baseline is being updated to make a red run green.
---

# eval-canary: prove the instrument holds still, then let it judge

A threshold may only block a merge once the measurement is stable. Temperature 0 makes a request reproducible in practice, not deterministic by construction, so stability is evidenced by replaying, never assumed.

## Procedure

1. Run the same harness, unchanged, on the same cases at least `canary_runs` times (default 3). Save each as a results file (`run1.json`, `run2.json`, ...).
2. Check them:

   ```bash
   eval-protocol canary run1.json run2.json run3.json
   ```

   It prints the spread per tier in percentage points, the cases that flipped, and whether a freeze is allowed.
3. If allowed, freeze:

   ```bash
   eval-protocol freeze run1.json run2.json run3.json --out eval/baselines/<target>.json
   ```

   Then gate on it: `eval-protocol verdict results.json --protocol eval/protocol.json --baseline eval/baselines/<target>.json`.
   A tier that drops by more than `max_regression_pp` (default 3) against the baseline is a FAIL even when it is still above its floor.

## The refusal rules (do not work around them)

- **A stand-in is never frozen.** A run that grades a mock, or answers copied from a document, passes by construction.
- **A red run is never frozen.** Freezing records a stable good state. It must never be used to turn a failing run green. If the user asks for that, say no, and say what the failing cases are.
- **Tier 1 must not move.** 0.00 points of spread, and no tier-1 case may flip. Tiers 2 and 3 may move inside their budget: demanding 0.00 everywhere is a bar that cannot be met, and a gate that cannot be met is a gate people learn to ignore.
- Enforcement can reintroduce variance (for example a conditional second model call on corrected answers). After such a change, replay the canary before trusting the old baseline.

## If the canary fails

Report the flipping cases. Do not lower a threshold or widen a budget to make it pass. Likely causes, in this order: temperature not actually 0, a nondeterministic provider, environment drift between runs, a grader that depends on wording. Fix the instrument, then replay.
