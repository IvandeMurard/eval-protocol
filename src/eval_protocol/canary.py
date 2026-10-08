"""Canary: the same input replayed on purpose, to prove the score is a measurement and not a draw."""
from __future__ import annotations

from dataclasses import dataclass, field

from .tiers import Protocol, Results, evaluate


@dataclass
class CanaryReport:
    runs: int
    # tier number -> spread in percentage points between the best and worst run
    tier_spread_pp: dict[int, float] = field(default_factory=dict)
    # (case_id, grader) pairs whose outcome differs between runs
    flipping: list[tuple[str, str]] = field(default_factory=list)

    def stable(self, tier: int) -> bool:
        return self.tier_spread_pp.get(tier, 0.0) == 0.0


def analyze(runs: list[Results], protocol: Protocol) -> CanaryReport:
    verdicts = [evaluate(r, protocol) for r in runs]
    spreads: dict[int, float] = {}
    for spec in protocol.tiers:
        rates = []
        for v in verdicts:
            tier = next((t for t in v.tiers if t.spec.tier == spec.tier), None)
            if tier is not None and tier.checked:
                rates.append(tier.rate)
        spreads[spec.tier] = (max(rates) - min(rates)) * 100 if rates else 0.0

    outcomes: dict[tuple[str, str], set[bool]] = {}
    for r in runs:
        for c in r.checks:
            outcomes.setdefault((c.case_id, c.grader), set()).add(c.passed)
    flipping = sorted(k for k, seen in outcomes.items() if len(seen) > 1)

    return CanaryReport(runs=len(runs), tier_spread_pp=spreads, flipping=flipping)
