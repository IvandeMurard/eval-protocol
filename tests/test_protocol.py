import json
import os
import tempfile
import unittest
from pathlib import Path

from eval_protocol import baseline as bl
from eval_protocol import canary as cn
from eval_protocol import dataset as ds
from eval_protocol.cli import main
from eval_protocol.scaffold import scaffold
from eval_protocol.tiers import (
    ERROR,
    FAIL,
    PASS,
    WARN,
    Check,
    Protocol,
    Results,
    Tier,
    evaluate,
)

PROTOCOL = Protocol(
    tiers=(
        Tier(1, "safety", 1.0, ("no-invented-figures", "no-contradiction")),
        Tier(2, "trust", 0.95, ("attribution",)),
        Tier(3, "form", 0.90, ("closing",)),
    )
)


def run(misses=(), cases=20, stand_in=False, target="t"):
    """`cases` cases, each graded by one grader per tier; `misses` are (case, grader) pairs."""
    graders = ["no-invented-figures", "attribution", "closing"]
    checks = [
        Check(f"c{i:02d}", g, (f"c{i:02d}", g) not in set(misses))
        for i in range(cases)
        for g in graders
    ]
    return Results(target=target, checks=checks, temperature=0, stand_in=stand_in)


class VerdictTests(unittest.TestCase):
    def test_clean_run_passes(self):
        self.assertEqual(evaluate(run(), PROTOCOL).code, PASS)

    def test_a_safety_tier_with_no_grader_does_not_pass_clean(self):
        unmapped = Protocol(tiers=(Tier(1, "safety", 1.0), Tier(2, "trust", 0.95), Tier(3, "form", 0.9)))
        verdict = evaluate(run(), unmapped)
        self.assertEqual(verdict.code, WARN)
        self.assertIn("vacuously", verdict.reasons[0])

    def test_empty_run_is_error_not_pass(self):
        self.assertEqual(evaluate(Results("t", []), PROTOCOL).code, ERROR)

    def test_high_pass_rate_still_fails_when_the_safety_tier_has_a_miss(self):
        # 61 of 64 is a failure when the misses sit in the tier with no budget.
        results = run(misses=[("c00", "no-invented-figures")], cases=64)
        verdict = evaluate(results, PROTOCOL)
        overall = sum(c.passed for c in results.checks) / len(results.checks)
        self.assertGreater(overall, 0.99)
        self.assertEqual(verdict.code, FAIL)
        self.assertIn("tier 1", verdict.reasons[0])

    def test_form_misses_inside_budget_warn_but_do_not_fail(self):
        verdict = evaluate(run(misses=[("c00", "closing")], cases=20), PROTOCOL)
        self.assertEqual(verdict.code, WARN)

    def test_form_misses_beyond_budget_fail(self):
        verdict = evaluate(run(misses=[("c00", "closing"), ("c01", "closing"), ("c02", "closing")]), PROTOCOL)
        self.assertEqual(verdict.code, FAIL)

    def test_unmapped_grader_cannot_block_and_is_reported(self):
        results = run()
        results.checks.append(Check("c00", "brand-new-grader", False))
        verdict = evaluate(results, PROTOCOL)
        self.assertEqual(verdict.unmapped_graders, ["brand-new-grader"])
        self.assertNotEqual(verdict.code, ERROR)
        # one miss in 61 tier-3 checks stays above the 90% floor
        self.assertEqual(verdict.code, WARN)


class BaselineTests(unittest.TestCase):
    def frozen(self, results):
        return bl.build_baseline(results, evaluate(results, PROTOCOL))

    def test_erosion_above_the_floor_is_a_regression(self):
        base = self.frozen(run(cases=100))
        # tier 2 goes from 100% to 96%: above its 95% floor, still a 4pp drop.
        now = run(misses=[(f"c{i:02d}", "attribution") for i in range(4)], cases=100)
        verdict = evaluate(now, PROTOCOL)
        self.assertNotEqual(verdict.code, FAIL)
        comparison = bl.compare(base, now, verdict, PROTOCOL)
        verdict = bl.apply_baseline(verdict, comparison)
        self.assertEqual(verdict.code, FAIL)
        self.assertEqual(len(comparison.regressions), 1)

    def test_small_flap_inside_the_regression_budget_is_not_a_failure(self):
        base = self.frozen(run(cases=100))
        now = run(misses=[("c00", "closing"), ("c01", "closing")], cases=100)
        verdict = evaluate(now, PROTOCOL)
        comparison = bl.compare(base, now, verdict, PROTOCOL)
        self.assertEqual(comparison.regressions, [])

    def test_swapping_one_failure_for_another_is_visible(self):
        base = self.frozen(run(misses=[("c00", "closing")], cases=100))
        now = run(misses=[("c01", "closing")], cases=100)
        comparison = bl.compare(base, now, evaluate(now, PROTOCOL), PROTOCOL)
        self.assertEqual(comparison.newly_failing, ["c01"])
        self.assertEqual(comparison.newly_passing, ["c00"])

    def test_baseline_round_trips(self):
        base = self.frozen(run())
        with tempfile.TemporaryDirectory() as d:
            path = bl.save_baseline(base, Path(d) / "x" / "b.json")
            self.assertEqual(bl.load_baseline(path), base)
        self.assertIsNone(bl.load_baseline("/nonexistent/baseline.json"))


class FreezeTests(unittest.TestCase):
    def test_three_identical_green_runs_may_be_frozen(self):
        self.assertIsNone(bl.freeze_refusal([run(), run(), run()], PROTOCOL))

    def test_too_few_runs(self):
        self.assertIn("needs >= 3", bl.freeze_refusal([run(), run()], PROTOCOL))

    def test_a_stand_in_is_never_frozen(self):
        refusal = bl.freeze_refusal([run(stand_in=True), run(), run()], PROTOCOL)
        self.assertIn("stand-in", refusal)

    def test_a_red_run_is_never_frozen(self):
        red = run(misses=[("c00", "no-invented-figures")])
        refusal = bl.freeze_refusal([run(), run(), red], PROTOCOL)
        self.assertIn("never frozen", refusal)

    def test_tier_one_must_not_move_but_tiers_two_and_three_may(self):
        moving = [run(), run(misses=[("c00", "closing")]), run(misses=[("c01", "closing")])]
        self.assertIsNone(bl.freeze_refusal(moving, PROTOCOL))

    def test_tier_one_cases_swapping_places_is_not_stable(self):
        # Same rate in every run, but a different tier-1 case fails each time. Not red here
        # because the protocol below gives tier 1 a budget; the flip alone must refuse.
        lenient = Protocol(
            tiers=(
                Tier(1, "safety", 0.90, ("no-invented-figures",)),
                Tier(2, "trust", 0.95, ("attribution",)),
                Tier(3, "form", 0.90, ("closing",)),
            )
        )
        runs = [
            run(misses=[("c00", "no-invented-figures")], cases=20),
            run(misses=[("c01", "no-invented-figures")], cases=20),
            run(misses=[("c02", "no-invented-figures")], cases=20),
        ]
        self.assertIn("flipped", bl.freeze_refusal(runs, lenient))

    def test_canary_reports_spread_and_flips(self):
        runs = [run(), run(misses=[("c00", "closing")]), run()]
        report = cn.analyze(runs, PROTOCOL)
        self.assertTrue(report.stable(1))
        self.assertFalse(report.stable(3))
        self.assertEqual(report.flipping, [("c00", "closing")])


class DatasetTests(unittest.TestCase):
    def write(self, text):
        d = tempfile.mkdtemp()
        path = Path(d) / "cases.jsonl"
        path.write_text(text, encoding="utf-8")
        return path

    def test_well_formed(self):
        line = json.dumps({"id": "a", "category": "x", "input": "q", "expected": "r", "failure_trigger": "t"})
        self.assertEqual(ds.validate(self.write(line + "\n")), [])

    def test_missing_failure_trigger_and_duplicate_id(self):
        good = {"id": "a", "category": "x", "input": "q", "expected": "r", "failure_trigger": "t"}
        bad = dict(good)
        del bad["failure_trigger"]
        errors = ds.validate(self.write(json.dumps(good) + "\n" + json.dumps(bad) + "\n"))
        self.assertTrue(any("failure_trigger" in e for e in errors))
        self.assertTrue(any("duplicate id" in e for e in errors))

    def test_empty_and_invalid(self):
        self.assertTrue(ds.validate(self.write("")))
        self.assertTrue(any("invalid JSON" in e for e in ds.validate(self.write("{nope\n"))))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def dump(self, name, results):
        path = self.dir / name
        path.write_text(
            json.dumps(
                {
                    "target": results.target,
                    "temperature": results.temperature,
                    "stand_in": results.stand_in,
                    "checks": [
                        {"case_id": c.case_id, "grader": c.grader, "passed": c.passed} for c in results.checks
                    ],
                }
            ),
            encoding="utf-8",
        )
        return str(path)

    def protocol_file(self):
        path = self.dir / "protocol.json"
        path.write_text(
            json.dumps(
                {
                    "tiers": [
                        {"tier": t.tier, "name": t.name, "threshold": t.threshold, "graders": list(t.graders)}
                        for t in PROTOCOL.tiers
                    ]
                }
            ),
            encoding="utf-8",
        )
        return str(path)

    def test_exit_code_is_the_verdict(self):
        proto = self.protocol_file()
        self.assertEqual(main(["verdict", self.dump("g.json", run()), "--protocol", proto]), PASS)
        red = self.dump("r.json", run(misses=[("c00", "no-invented-figures")]))
        self.assertEqual(main(["verdict", red, "--protocol", proto]), FAIL)

    def test_unreadable_results_is_error_not_fail(self):
        self.assertEqual(main(["verdict", str(self.dir / "missing.json")]), ERROR)

    def test_freeze_then_gate_on_the_baseline(self):
        proto = self.protocol_file()
        runs = [self.dump(f"r{i}.json", run()) for i in range(3)]
        out = str(self.dir / "baselines" / "t.json")
        self.assertEqual(main(["freeze", *runs, "--out", out, "--protocol", proto]), PASS)
        self.assertTrue(os.path.exists(out))
        worse = self.dump("w.json", run(misses=[(f"c{i:02d}", "attribution") for i in range(2)], cases=20))
        # 2 of 20 tier-2 checks = 90% < 95%: fails on the absolute floor as well
        self.assertEqual(main(["verdict", worse, "--protocol", proto, "--baseline", out]), FAIL)

    def test_freeze_refuses_a_stand_in(self):
        runs = [self.dump(f"s{i}.json", run(stand_in=True)) for i in range(3)]
        out = str(self.dir / "b.json")
        self.assertEqual(main(["freeze", *runs, "--out", out]), FAIL)
        self.assertFalse(os.path.exists(out))

    def test_init_scaffolds_and_never_overwrites(self):
        created, skipped = scaffold(self.dir)
        self.assertEqual(len(created), 4)
        self.assertEqual(skipped, [])
        (self.dir / "eval" / "protocol.json").write_text("{}", encoding="utf-8")
        created, skipped = scaffold(self.dir)
        self.assertEqual(created, [])
        self.assertEqual((self.dir / "eval" / "protocol.json").read_text(), "{}")

    def test_scaffolded_protocol_and_case_set_load(self):
        scaffold(self.dir)
        self.assertEqual(main(["validate-dataset", str(self.dir / "eval" / "cases.jsonl")]), PASS)
        r = self.dump("g.json", run())
        # No grader is assigned to a tier yet: the safety tier passes vacuously, and says so.
        self.assertEqual(main(["verdict", r, "--protocol", str(self.dir / "eval" / "protocol.json")]), WARN)


if __name__ == "__main__":
    unittest.main()
