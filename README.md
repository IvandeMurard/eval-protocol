# eval-protocol

The rules that decide whether an LLM agent's evaluation is allowed to block a release. Not another harness: you keep yours. This is the layer that turns its results into a decision you can defend, and refuses the shortcuts that make a green gate meaningless.

- **Tiers with budgets.** 61 checks out of 64 is a failure when the misses are in the tier with no budget.
- **One exit-code contract.** `0` PASS, `1` FAIL, `2` ERROR (nothing was measured), `3` WARN (within budget, not clean).
- **Frozen baselines with a relative-regression rule.** A tier that drops more than 3 points fails even above its floor.
- **A canary rule for freezing.** A baseline is frozen only from stable, green, real runs: never from a stand-in, never from a red run, and tier 1 must not move.
- **A case-set validator.** Every case states its `failure_trigger` in advance.

Standard library only. Python 3.9+. MIT.

It also ships as three agent skills (`skills/`) that follow the open `SKILL.md` format and as a Claude Code plugin.

Background: [Evaluating LLM agents: how would you know it had stopped working?](https://ivandemurard.com/journal/harnesses-graders-closed-loops). The protocol itself is in [`docs/PROTOCOL.md`](docs/PROTOCOL.md); where each mechanism comes from is in [`PROVENANCE.md`](PROVENANCE.md).

## Quick start

```bash
pip install git+https://github.com/IvandeMurard/eval-protocol
eval-protocol init .                       # eval/protocol.json, eval/cases.jsonl, CI template
eval-protocol validate-dataset eval/cases.jsonl
eval-protocol verdict eval/results.json --protocol eval/protocol.json
```

Your harness writes `eval/results.json`:

```json
{"target": "offline", "temperature": 0, "stand_in": false,
 "checks": [{"case_id": "c01", "grader": "no-invented-figures", "passed": true}]}
```

Try it on the [illustrative 61-of-64 example](examples/illustrative-61-of-64):

```bash
eval-protocol verdict examples/illustrative-61-of-64/results.json \
  --protocol examples/illustrative-61-of-64/protocol.json     # exit 1
```

Freeze a baseline, then gate on it:

```bash
eval-protocol canary run1.json run2.json run3.json
eval-protocol freeze run1.json run2.json run3.json --out eval/baselines/offline.json
eval-protocol verdict results.json --protocol eval/protocol.json --baseline eval/baselines/offline.json
```

## Use it from an agent

As Agent Skills (Claude Code, Codex CLI, Gemini CLI, Cursor and other tools that read `SKILL.md`):

```bash
npx skills add IvandeMurard/eval-protocol
```

As a Claude Code plugin:

```
/plugin marketplace add IvandeMurard/eval-protocol
/plugin install eval-protocol@eval-protocol
```

| Skill | Use it to |
| --- | --- |
| `eval-init` | define "working" before the model code: case set, tiers, gate |
| `eval-canary` | prove the measurement holds still, and freeze a baseline safely |
| `eval-audit` | find the ways an eval setup lies |

The install commands above follow the documentation of those tools and have not been tested end to end yet.

## What this does not do

- It does not run your model or grade answers. Graders are yours; prefer pure functions for anything in tier 1.
- It does not cover the runtime or outcome arms of evaluation (production signals, whether reality proved the output right). It is the offline gate.
- It is v0.1, extracted from two systems by one author. Treat it as a reference implementation, not a standard.

Not ported yet: path-triggered gating with a hash cache, category coverage, a calibrated LLM-judge check, drift tests.

## Develop

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

MIT. © Ivan de Murard.
