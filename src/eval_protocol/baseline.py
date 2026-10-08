"""Frozen baselines, regression diffs, and the rule for when one may be frozen.

Absolute thresholds catch a collapse. They do not catch erosion: a change that
takes a tier from 100% to 96% is still above its floor and has still broken
something. The baseline is what makes the relative-regression rule enforceable.

A baseline is only meaningful if the measurement is stable, and it must never be
frozen to turn a red run green. `freeze_refusal` encodes both.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .tiers import FAIL, ERROR, Protocol, ProtocolError, Results, Verdict, evaluate


@dataclass
class Baseline:
    target: str
    recorded_at: str
    temperature: float | None
    # tier number (as a string) -> fraction held
    tier_rates: dict[str, float]
    # case id -> every grader held. A swap of one failure for another stays visible.
    cases: dict[str, bool]
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "target": self.target,
                "recorded_at": self.recorded_at,
                "temperature": self.temperature,
                "tier_rates": self.tier_rates,
                "cases": dict(sorted(self.cases.items())),
                "note": self.note,
            },
            indent=2,
        ) + "\n"


def case_outcomes(results: Results) -> dict[str, bool]:
    outcomes: dict[str, bool] = {}
    for c in results.checks:
        outcomes[c.case_id] = outcomes.get(c.case_id, True) and c.passed
    return outcomes


def build_baseline(results: Results, verdict: Verdict, note: str = "") -> Baseline:
    return Baseline(
        target=results.target,
        recorded_at=date.today().isoformat(),
        temperature=results.temperature,
        tier_rates={str(t.spec.tier): t.rate for t in verdict.tiers if t.checked},
        cases=case_outcomes(results),
        note=note or results.note,
    )


def save_baseline(baseline: Baseline, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(baseline.to_json(), encoding="utf-8")
    return path


def load_baseline(path: str | Path) -> Baseline | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return Baseline(
            target=str(raw["target"]),
            recorded_at=str(raw["recorded_at"]),
            temperature=raw.get("temperature"),
            tier_rates={str(k): float(v) for k, v in raw["tier_rates"].items()},
            cases={str(k): bool(v) for k, v in raw["cases"].items()},
            note=str(raw.get("note", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError(f"cannot read baseline {path}: {exc}") from exc


@dataclass
class Comparison:
    regressions: list[str] = field(default_factory=list)  # tier drops beyond the budget: hard failures
    newly_failing: list[str] = field(default_factory=list)
    newly_passing: list[str] = field(default_factory=list)
    drift_notes: list[str] = field(default_factory=list)


def compare(baseline: Baseline, results: Results, verdict: Verdict, protocol: Protocol) -> Comparison:
    out = Comparison()

    for t in verdict.tiers:
        if not t.checked:
            continue
        was = baseline.tier_rates.get(str(t.spec.tier))
        if was is None:
            continue
        drop_pp = (was - t.rate) * 100
        if drop_pp > protocol.max_regression_pp:
            out.regressions.append(
                f"tier {t.spec.tier} ({t.spec.name}) dropped {drop_pp:.1f}pp: "
                f"{was * 100:.1f}% -> {t.rate * 100:.1f}% (max {protocol.max_regression_pp:g}pp)"
            )

    current = case_outcomes(results)
    for case_id, passed in sorted(current.items()):
        was_case = baseline.cases.get(case_id)
        if was_case is None:
            out.drift_notes.append(f"{case_id} is new since the baseline")
        elif was_case and not passed:
            out.newly_failing.append(case_id)
        elif not was_case and passed:
            out.newly_passing.append(case_id)
    for case_id in sorted(baseline.cases):
        if case_id not in current:
            out.drift_notes.append(f"{case_id} was in the baseline but did not run")
    return out


def apply_baseline(verdict: Verdict, comparison: Comparison) -> Verdict:
    """A regression against the baseline is a FAIL even when every tier is above its floor."""
    if comparison.regressions and verdict.code != ERROR:
        verdict.code = FAIL
        verdict.reasons.extend(f"regression: {r}" for r in comparison.regressions)
    return verdict


def freeze_refusal(runs: list[Results], protocol: Protocol) -> str | None:
    """Why these runs may NOT be frozen as a baseline, or None if they may.

    The rules, in the order a reviewer would ask:

    1. A stand-in is never a baseline. It passes by construction.
    2. A baseline is never frozen from a red run. Freezing is for recording a
       stable good state, never for turning a failing run green.
    3. Enough identical runs. Temperature 0 makes a request reproducible in
       practice, not deterministic by construction, so stability is evidenced
       by replaying, not assumed.
    4. Tier 1 must show 0.00 points of variance across the runs, and no tier-1
       case may flip. Tiers 2 and 3 may move inside their budget: demanding 0.00
       everywhere sets a bar that cannot be met, and a gate that cannot be met
       is a gate people learn to ignore.
    """
    if len(runs) < protocol.canary_runs:
        return f"canary needs >= {protocol.canary_runs} runs, got {len(runs)}"

    if any(r.stand_in for r in runs):
        return "a stand-in run is never frozen as a baseline: it grades something other than what ships"

    verdicts = [evaluate(r, protocol) for r in runs]
    for v in verdicts:
        if v.code in (FAIL, ERROR):
            return f"a {v.label} run is never frozen: freezing must not turn a red run green"

    first_tier = min(spec.tier for spec in protocol.tiers)
    tier1_rates = []
    for v in verdicts:
        tier = next((t for t in v.tiers if t.spec.tier == first_tier), None)
        tier1_rates.append(tier.rate if tier else 1.0)
    spread_pp = (max(tier1_rates) - min(tier1_rates)) * 100
    if spread_pp != 0:
        return f"tier {first_tier} varies by {spread_pp:.2f}pp across runs: the instrument is not holding still"

    tier1_graders = {g for spec in protocol.tiers if spec.tier == first_tier for g in spec.graders}
    per_run: list[dict[tuple[str, str], bool]] = [
        {(c.case_id, c.grader): c.passed for c in r.checks if c.grader in tier1_graders}
        for r in runs
    ]
    flipped = sorted({k for run in per_run for k in run if len({r.get(k) for r in per_run}) > 1})
    if flipped:
        shown = ", ".join(f"{case}:{grader}" for case, grader in flipped[:5])
        return f"tier {first_tier} cases flipped between runs ({shown}): not stable"

    return None
