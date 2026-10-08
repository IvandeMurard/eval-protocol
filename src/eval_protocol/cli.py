"""Command line: `eval-protocol <command>`. The exit code is the verdict."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import baseline as bl
from . import canary as cn
from . import dataset as ds
from . import report
from .scaffold import scaffold
from .tiers import (
    DEFAULT_PROTOCOL,
    ERROR,
    FAIL,
    LABELS,
    PASS,
    Protocol,
    ProtocolError,
    evaluate,
    load_protocol,
    load_results,
)


def _protocol(path: str | None) -> Protocol:
    if path is None:
        return DEFAULT_PROTOCOL
    return load_protocol(path)


def cmd_verdict(args: argparse.Namespace) -> int:
    protocol = _protocol(args.protocol)
    results = load_results(args.results)
    verdict = evaluate(results, protocol)

    comparison = None
    if args.baseline:
        base = bl.load_baseline(args.baseline)
        if base is None:
            print(f"note: no baseline at {args.baseline}; absolute thresholds only", file=sys.stderr)
        else:
            comparison = bl.compare(base, results, verdict, protocol)
            verdict = bl.apply_baseline(verdict, comparison)

    text = report.render(verdict, comparison, results.target)
    print(text)
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    if results.stand_in:
        print(
            "warning: this run is marked stand_in. It checks the plumbing, not the product.",
            file=sys.stderr,
        )
    return verdict.code


def cmd_canary(args: argparse.Namespace) -> int:
    protocol = _protocol(args.protocol)
    runs = [load_results(p) for p in args.results]
    if len(runs) < 2:
        print("error: a canary needs at least two runs of the same input", file=sys.stderr)
        return ERROR
    rep = cn.analyze(runs, protocol)
    print(f"{rep.runs} runs")
    for spec in protocol.tiers:
        spread = rep.tier_spread_pp.get(spec.tier, 0.0)
        print(f"  tier {spec.tier} ({spec.name}): spread {spread:.2f}pp")
    if rep.flipping:
        print("  cases that flipped: " + ", ".join(f"{c}:{g}" for c, g in rep.flipping))
    refusal = bl.freeze_refusal(runs, protocol)
    print("freeze: " + ("allowed" if refusal is None else f"REFUSED, {refusal}"))
    return PASS if refusal is None else FAIL


def cmd_freeze(args: argparse.Namespace) -> int:
    protocol = _protocol(args.protocol)
    runs = [load_results(p) for p in args.results]
    refusal = bl.freeze_refusal(runs, protocol)
    if refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return FAIL
    verdict = evaluate(runs[0], protocol)
    path = bl.save_baseline(bl.build_baseline(runs[0], verdict, args.note or ""), args.out)
    print(f"baseline frozen: {path}")
    return PASS


def cmd_validate(args: argparse.Namespace) -> int:
    errors = ds.validate(args.dataset)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} problem(s) in {args.dataset}", file=sys.stderr)
        return FAIL
    print(f"{args.dataset}: ok")
    return PASS


def cmd_init(args: argparse.Namespace) -> int:
    created, skipped = scaffold(Path(args.directory))
    for p in created:
        print(f"created  {p}")
    for p in skipped:
        print(f"exists   {p} (left untouched)")
    return PASS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval-protocol",
        description="Tiered acceptance criteria, frozen baselines and a canary rule for LLM evaluation. "
        f"Exit codes: {', '.join(f'{k}={v}' for k, v in LABELS.items())}.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("verdict", help="grade a results file against the protocol")
    v.add_argument("results", help="results JSON: {target, checks: [{case_id, grader, passed}]}")
    v.add_argument("--protocol", help="protocol JSON (default: three generic tiers)")
    v.add_argument("--baseline", help="frozen baseline JSON; a regression beyond the budget is a FAIL")
    v.add_argument("--md", help="also write the Markdown report to this path")
    v.set_defaults(func=cmd_verdict)

    c = sub.add_parser("canary", help="compare N runs of the same input; say whether a baseline may be frozen")
    c.add_argument("results", nargs="+")
    c.add_argument("--protocol")
    c.set_defaults(func=cmd_canary)

    f = sub.add_parser("freeze", help="freeze a baseline, only if the canary rule allows it")
    f.add_argument("results", nargs="+", help="the runs (at least `canary_runs` of them); the first is recorded")
    f.add_argument("--out", required=True)
    f.add_argument("--protocol")
    f.add_argument("--note")
    f.set_defaults(func=cmd_freeze)

    d = sub.add_parser("validate-dataset", help="check a JSONL case set is well formed")
    d.add_argument("dataset")
    d.set_defaults(func=cmd_validate)

    i = sub.add_parser("init", help="scaffold eval/ (protocol, case set, baselines) and a CI gate template")
    i.add_argument("directory", nargs="?", default=".")
    i.set_defaults(func=cmd_init)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ProtocolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    raise SystemExit(main())
