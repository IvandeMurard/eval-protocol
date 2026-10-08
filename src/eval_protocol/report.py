"""Markdown report for a verdict, suitable for a sticky pull-request comment."""
from __future__ import annotations

from .baseline import Comparison
from .tiers import Verdict


def render(verdict: Verdict, comparison: Comparison | None = None, target: str = "") -> str:
    title = f"## Eval gate: {verdict.label}" + (f" ({target})" if target else "")
    lines = [title, ""]

    if verdict.tiers:
        lines += ["| Tier | Held | Rate | Required | |", "| --- | --- | --- | --- | --- |"]
        for t in verdict.tiers:
            mark = "ok" if t.meets_threshold else "BELOW"
            lines.append(
                f"| {t.spec.tier} {t.spec.name} | {t.held}/{t.checked} | "
                f"{t.rate * 100:.1f}% | {t.spec.threshold * 100:.0f}% | {mark} |"
            )
        lines.append("")

    if verdict.reasons:
        lines += [f"- {r}" for r in verdict.reasons] + [""]

    for t in verdict.tiers:
        if t.failures:
            lines.append(f"**Tier {t.spec.tier} misses:** " + ", ".join(f"`{f}`" for f in t.failures))
    if any(t.failures for t in verdict.tiers):
        lines.append("")

    if verdict.unmapped_graders:
        lines.append(
            "Graders not assigned to a tier (treated as the last tier until someone decides their severity): "
            + ", ".join(f"`{g}`" for g in verdict.unmapped_graders)
        )
        lines.append("")

    if comparison is not None:
        if comparison.newly_failing:
            lines.append("**Held at baseline, fail now:** " + ", ".join(f"`{c}`" for c in comparison.newly_failing))
        if comparison.newly_passing:
            lines.append("**Failed at baseline, hold now:** " + ", ".join(f"`{c}`" for c in comparison.newly_passing))
        for note in comparison.drift_notes:
            lines.append(f"- drift: {note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
