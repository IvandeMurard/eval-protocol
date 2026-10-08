"""Tiered acceptance criteria: what "passing" means.

A pass rate with no threshold attached is a number, not a decision. A protocol
assigns every grader to a severity tier, gives each tier its own budget, and
turns the results into one verdict with an exit code.

Exit-code contract (the same everywhere in this package):

    0  PASS   every tier at 100%
    1  FAIL   a tier is below its threshold, or a tier regressed against the baseline
    2  ERROR  the harness crashed or measured nothing. No measurement was taken.
    3  WARN   thresholds met, but a tier is not clean. Not a synonym for "fine".

ERROR is kept apart from FAIL on purpose: "no measurement" and "the measurement
came back bad" call for opposite actions, and a CI that conflates them reads a
crash as a quality signal.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

PASS = 0
FAIL = 1
ERROR = 2
WARN = 3

LABELS = {PASS: "PASS", FAIL: "FAIL", ERROR: "ERROR", WARN: "WARN"}

# A new grader must not be able to block a run before someone has decided how
# severe its failures are, so graders that no tier claims fall into the last tier.
DEFAULT_TIER = 3


class ProtocolError(ValueError):
    """The protocol file or a results file is unusable. Maps to exit code 2."""


@dataclass(frozen=True)
class Tier:
    tier: int
    name: str
    threshold: float  # fraction of checks that must hold; 1.0 = no failures tolerated
    graders: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class Protocol:
    tiers: tuple[Tier, ...]
    max_regression_pp: float = 3.0
    canary_runs: int = 3

    def tier_of(self, grader: str) -> int:
        for spec in self.tiers:
            if grader in spec.graders:
                return spec.tier
        return DEFAULT_TIER

    def unmapped(self, graders: Iterable[str]) -> list[str]:
        claimed = {g for spec in self.tiers for g in spec.graders}
        return sorted({g for g in graders if g not in claimed})


DEFAULT_PROTOCOL = Protocol(
    tiers=(
        Tier(1, "safety", 1.00, (), "Failures that can cause real harm. No budget."),
        Tier(2, "trust", 0.95, (), "Usable when degraded, but erodes the reason to trust the system."),
        Tier(3, "form", 0.90, (), "Wording and discipline. A miss misleads nobody about a limit."),
    ),
)


def load_protocol(path: str | Path) -> Protocol:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        tiers = tuple(
            Tier(
                tier=int(t["tier"]),
                name=str(t["name"]),
                threshold=float(t["threshold"]),
                graders=tuple(t.get("graders", ())),
                rationale=str(t.get("rationale", "")),
            )
            for t in raw["tiers"]
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ProtocolError(f"cannot read protocol {path}: {exc}") from exc

    if not tiers:
        raise ProtocolError("protocol defines no tiers")
    if len({t.tier for t in tiers}) != len(tiers):
        raise ProtocolError("protocol defines the same tier number twice")
    for t in tiers:
        if not 0.0 <= t.threshold <= 1.0:
            raise ProtocolError(f"tier {t.tier}: threshold must be between 0 and 1")

    return Protocol(
        tiers=tuple(sorted(tiers, key=lambda t: t.tier)),
        max_regression_pp=float(raw.get("max_regression_pp", 3.0)),
        canary_runs=int(raw.get("canary_runs", 3)),
    )


@dataclass(frozen=True)
class Check:
    case_id: str
    grader: str
    passed: bool
    reason: str = ""


@dataclass
class Results:
    """One run of a harness: a list of checks plus what was measured."""

    target: str
    checks: list[Check]
    temperature: float | None = None
    # True when the run graded a mock, a stand-in or a copy of a document rather
    # than what ships. Such a run may gate a pipeline; it may never be frozen
    # as a baseline.
    stand_in: bool = False
    note: str = ""


def load_results(path: str | Path) -> Results:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        checks = [
            Check(
                case_id=str(c["case_id"]),
                grader=str(c["grader"]),
                passed=bool(c["passed"]),
                reason=str(c.get("reason", "")),
            )
            for c in raw["checks"]
        ]
        return Results(
            target=str(raw.get("target", "default")),
            checks=checks,
            temperature=raw.get("temperature"),
            stand_in=bool(raw.get("stand_in", False)),
            note=str(raw.get("note", "")),
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ProtocolError(f"cannot read results {path}: {exc}") from exc


@dataclass
class TierResult:
    spec: Tier
    checked: int
    held: int
    rate: float
    meets_threshold: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    code: int
    reasons: list[str]
    tiers: list[TierResult]
    unmapped_graders: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return LABELS[self.code]


def evaluate(results: Results, protocol: Protocol = DEFAULT_PROTOCOL) -> Verdict:
    """Turn a run into a verdict.

    A tier fails when its rate is below its threshold, however good the overall
    pass rate is: 61 checks out of 64 is a failure when the misses sit in the
    tier with no budget.
    """
    if not results.checks:
        return Verdict(ERROR, ["no checks in the run: nothing was measured"], [])

    tiers: list[TierResult] = []
    for spec in protocol.tiers:
        relevant = [c for c in results.checks if protocol.tier_of(c.grader) == spec.tier]
        held = sum(1 for c in relevant if c.passed)
        rate = 1.0 if not relevant else held / len(relevant)
        tiers.append(
            TierResult(
                spec=spec,
                checked=len(relevant),
                held=held,
                rate=rate,
                meets_threshold=rate >= spec.threshold,
                failures=sorted({f"{c.case_id}:{c.grader}" for c in relevant if not c.passed}),
            )
        )

    reasons: list[str] = []
    code = PASS
    for t in tiers:
        if t.meets_threshold:
            continue
        code = FAIL
        reasons.append(
            f"tier {t.spec.tier} ({t.spec.name}): {t.rate * 100:.1f}% held, "
            f"{t.spec.threshold * 100:.0f}% required"
        )

    # A top tier that checked nothing passes vacuously. That is the green gate on
    # something nobody measures, so it is surfaced rather than reported as clean.
    top = tiers[0]
    if code == PASS and top.checked == 0:
        code = WARN
        reasons.append(
            f"tier {top.spec.tier} ({top.spec.name}): no grader is assigned to it, so it passes vacuously"
        )

    # Meeting every threshold without being clean is worth surfacing but does not
    # block: tiers 2 and 3 have deliberate budgets.
    if code in (PASS, WARN):
        for t in tiers:
            if t.checked and t.rate < 1.0:
                code = WARN
                reasons.append(
                    f"tier {t.spec.tier} ({t.spec.name}): within budget at "
                    f"{t.rate * 100:.1f}%, but not clean"
                )

    return Verdict(
        code=code,
        reasons=reasons,
        tiers=tiers,
        unmapped_graders=protocol.unmapped(c.grader for c in results.checks),
    )
