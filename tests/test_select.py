import json
import tempfile
import unittest
from pathlib import Path

from eval_protocol import select as sel
from eval_protocol.cli import main
from eval_protocol.tiers import FAIL, PASS, WARN, Check, Protocol, Results, Tier, evaluate

CONFIG = {
    "layers": ["forecast", "parser", "memory"],
    "triggers": [
        {"paths": ["app/forecast/*"], "layers": ["forecast"]},
        {"paths": ["app/providers/*"], "layers": "all"},
        {"paths": ["prompts/*"], "layers": ["parser", "memory"]},
    ],
    "exempt_label": "eval-exempt",
}


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for rel in ["app/forecast/model.py", "app/providers/llm.py", "prompts/reply.txt", "docs/readme.md"]:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(rel, encoding="utf-8")

    def pick(self, files, labels=(), cache=None):
        return sel.select(files, CONFIG, labels, cache, self.root)

    def test_docs_only_change_runs_nothing(self):
        s = self.pick(["docs/readme.md"])
        self.assertTrue(s.skip)
        self.assertEqual(s.layers, [])

    def test_a_service_runs_its_layer_only(self):
        self.assertEqual(self.pick(["app/forecast/model.py"]).layers, ["forecast"])

    def test_a_provider_change_runs_everything(self):
        self.assertEqual(self.pick(["app/providers/llm.py"]).layers, ["forecast", "parser", "memory"])

    def test_nested_paths_match(self):
        (self.root / "app/forecast/sub").mkdir()
        (self.root / "app/forecast/sub/x.py").write_text("x", encoding="utf-8")
        self.assertEqual(self.pick(["app/forecast/sub/x.py"]).layers, ["forecast"])

    def test_exempt_label_skips_but_reports_what_was_touched(self):
        s = self.pick(["prompts/reply.txt"], labels=["eval-exempt"])
        self.assertTrue(s.skip)
        self.assertEqual(s.touched, ["prompts/reply.txt"])

    def test_cache_skips_identical_files_and_not_changed_ones(self):
        first = self.pick(["app/forecast/model.py"])
        self.assertFalse(first.skip)
        self.assertTrue(self.pick(["app/forecast/model.py"], cache={first.cache_key: "PASS"}).skip)
        (self.root / "app/forecast/model.py").write_text("changed", encoding="utf-8")
        self.assertFalse(self.pick(["app/forecast/model.py"], cache={first.cache_key: "PASS"}).skip)

    def test_config_with_unknown_layer_is_rejected(self):
        bad = self.root / "bad.json"
        bad.write_text(json.dumps({"layers": ["a"], "triggers": [{"paths": ["x/*"], "layers": ["b"]}]}), encoding="utf-8")
        with self.assertRaises(Exception):
            sel.load_config(bad)

    def test_cli_select_and_cache_record(self):
        cfg = self.root / "triggers.json"
        cfg.write_text(json.dumps(CONFIG), encoding="utf-8")
        cache = self.root / "cache.json"
        self.assertEqual(main(["select", "--config", str(cfg), "--files", "docs/readme.md"]), PASS)
        self.assertEqual(main(["cache-record", "abc", "--cache", str(cache)]), PASS)
        self.assertIn("abc", json.loads(cache.read_text()))


class CoverageTests(unittest.TestCase):
    PROTO = Protocol(tiers=(Tier(1, "safety", 1.0, ("g",)),), coverage_warn_below=0.8, coverage_fail_below=0.6)

    def run_with(self, failing_categories, categories=("a", "b", "c", "d", "e")):
        checks = [Check(f"{cat}-1", "g", cat not in failing_categories, category=cat) for cat in categories]
        # tier 1 must stay clean for the coverage rule to be the only signal: use a second grader outside tier 1
        checks = [Check(c.case_id, "form", c.passed, category=c.category) for c in checks] + \
                 [Check(f"{cat}-1", "g", True, category=cat) for cat in categories]
        return evaluate(Results("t", checks), self.PROTO)

    def test_full_coverage_does_not_add_a_reason(self):
        v = self.run_with(set())
        self.assertEqual(v.coverage, 1.0)
        self.assertFalse(any("coverage" in r for r in v.reasons))

    def test_coverage_between_thresholds_warns(self):
        v = self.run_with({"a", "b"}, categories=("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"))
        self.assertAlmostEqual(v.coverage, 0.8)
        v = self.run_with({"a", "b", "c"}, categories=("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"))
        self.assertEqual(v.code, WARN)

    def test_coverage_below_floor_fails(self):
        v = self.run_with({"a", "b", "c"})
        self.assertEqual(v.coverage, 0.4)
        self.assertEqual(v.code, FAIL)

    def test_coverage_configured_without_categories_is_not_silent(self):
        v = evaluate(Results("t", [Check("c", "g", True)]), self.PROTO)
        self.assertEqual(v.code, WARN)
        self.assertIsNone(v.coverage)


if __name__ == "__main__":
    unittest.main()
