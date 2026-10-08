# Provenance

Where each mechanism comes from. Two systems by the same author, one public, one private; this package was extracted from both, not copied from either.

| Mechanism | Origin | Where |
| --- | --- | --- |
| Three tiers with budgets (100/95/90), tier assignment of graders, verdict logic | Lore (public, TypeScript) | `frontend/evals/acceptance.ts` in [IvandeMurard/Lore](https://github.com/IvandeMurard/Lore) |
| Exit-code contract 0/1/2/3 | Aetherix (private, Python), reimplemented in Lore | `scripts/ci/check_eval_coverage.py`; Lore's `acceptance.ts` cites it |
| Relative regression of 3 points against a frozen baseline; per-case outcomes | Aetherix and Lore | Aetherix `scripts/eval/baselines.py`; Lore `frontend/evals/baseline.ts` |
| Refusal to freeze a stand-in or an unstable run | Aetherix | `parser_baseline_freeze_refusal` in `scripts/eval/baselines.py`. Extended here: a red run is never frozen, and the variance rule applies to tier 1 only |
| Canary rule corrected to "0.00 points on tier 1 only" | Lore | Section 7 of the article |
| `failure_trigger` on every case | Aetherix | `eval/golden_dataset.jsonl`, `scripts/eval/validate_dataset.py` |
| Graders as pure functions, offline regression suite of known-bad answers | Lore | `frontend/evals/README.md` |
| Path-triggered selection, sha256 cache of touched files, `eval-exempt` label (v0.2) | Aetherix | `scripts/ci/check_eval_coverage.py`, described publicly in [EVAL_GATE.md](https://github.com/IvandeMurard/Hospitality-Multi-agent-Architecture/blob/main/EVAL_GATE.md) |
| Coverage counted by category, with warn and fail floors (v0.2) | Aetherix | same file; the 80% and 60% defaults are Aetherix's |
| Six-question diagnostic (`eval-diagnose`, v0.2) | The article | its self-diagnostic block |

What the Aetherix repository does that is **not** ported: sticky pull-request comment, judge calibration (kappa), drift tests, interval calibration. Aetherix's own measurements run on a synthetic series and a stand-in parser; see the article.

The Aetherix repository is private. Lore's runs are replayable:

```bash
git clone https://github.com/IvandeMurard/Lore && cd Lore/frontend
npm ci && npx tsx evals/runner.ts --target regression
```
