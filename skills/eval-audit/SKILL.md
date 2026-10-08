---
name: eval-audit
description: Audit an LLM evaluation setup for the ways it can lie - graders too weak to fail a real defect, graders too strict to be believed, a gate that grades a stand-in, missing tiers, an all-green run nobody read. Use when an eval suite passes everything, when reviewing someone else's eval harness, or before trusting a green gate.
---

# eval-audit: who grades the grader

A grader written by the prompt's author inherits the author's blind spots. Audit in this order and report findings with evidence (file and line, or the exact answer), not impressions.

## 1. Read the passing answers, not only the failing ones

A run that passes everything has stopped being an instrument of discovery and become a safety net. Pull a sample of passing answers, especially for tier 1, and read them. For each, ask: would the required pattern also accept a wrong answer? (Example of a real defect: a required-content check accepted "NORMAL" because the word appeared in an answer that wrongly asserted NORMAL.)

## 2. Prove graders reject bad answers

A regression suite of known-bad answers, mostly verbatim model outputs, each expected to be rejected *by the right grader*, offline and free. Check it exists. A regression suite proves graders reject bad answers; it never proves they accept good ones phrased differently, which needs a real run.

## 3. Check what the gate actually grades

List every quality number the project reports and ask what produced it. Flag any that come from a mock, a stub, a rule-based stand-in, or hand-written reference answers. Those measure the ruler, not the product. They are legitimate as plumbing checks and must be labelled as such (`"stand_in": true`).

## 4. Tiers and thresholds

- Is there a tier with no budget for failures that cause real harm? Is any grader assigned to it? (`eval-protocol verdict` warns when the top tier is empty.)
- Is there a relative-regression rule against a frozen baseline, or only an absolute floor?
- Were baselines frozen after a canary, or after a lucky run?

## 5. Adversarial coverage

Look for cases written *against* the system, not for it: exact band boundaries, a second source contradicting the first, fluent answers carrying a wrong figure, text in retrieved content shaped like an instruction, social pressure to grant permission, manufactured agreement from a single source.

## 6. Signals nobody can see

Without typed signals in production (refusal reason, retrieval score, latency), drift shows up one release late. Say whether the runtime and outcome arms exist. Do not infer that they do.

## Output

A short list: finding, evidence, severity (does it let a tier-1 defect through?), smallest fix. End with what you did not check.
