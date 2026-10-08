---
name: eval-diagnose
description: Diagnose where an LLM product's evaluation is weakest, in six yes/no questions asked in dependency order, and point to the first gap. Use when someone asks whether their agent's evaluation is good enough, how they would know it stopped working, or where to start with evals.
---

# eval-diagnose: find the first gap

Six questions, in the order the layers depend on each other. Ask them one at a time. Stop at the **first "no"**: that is where to start, because nothing after it can be trusted until it holds.

Answers are self-declared. The diagnosis says where to look first, not whether the system is sound. Do not upgrade a "sort of" to a "yes": treat it as "no".

| # | Arm | Question | If "no" |
|---|---|---|---|
| 1 | Offline | Is there a set of cases with known correct answers, edge cases included, written before or with the model code? | Nothing above it can be measured. Write the case set and a definition of failure first (`eval-init`). |
| 2 | Offline | Does each kind of failure have its own threshold, and can a breach of the worst kind block a release on its own, whatever the pass rate? | A pass rate with no threshold is a number, not a decision. 61 out of 64 can be a failure. Set tiers with budgets (`eval-init`). |
| 3 | Offline | Have the same inputs been replayed several times, with the same score, before any threshold was allowed to block? | Until the instrument holds still, a threshold blocks on the draw, not on the work (`eval-canary`). |
| 4 | Offline | Is every reported quality number produced by what actually ships: the real model on the real path, not a stand-in, a mock or a copied target? | A stand-in written against the same cases passes by construction (`eval-audit`). |
| 5 | Runtime | In production, does each layer emit a typed signal (refusal reason, retrieval score, latency) that can alert before a user notices? | Drift shows up one release late, or when someone complains. |
| 6 | Outcome | Do you learn whether each output was acted on and whether reality proved it right, with overrides recorded as data? | You measure but never learn, and no confidence score can be calibrated. |

## Procedure

1. Ask question 1. Wait for the answer. Ask for one piece of evidence (a file, a command, a dashboard) before accepting a "yes".
2. Continue in order. At the first "no", stop and give: the gap in one sentence, the next concrete step, and the skill or section that covers it.
3. If all six are "yes", ask the next question: who wrote the graders, and has anyone tried to break them? Then run `eval-audit`.

## Source

From the self-diagnostic in [Evaluating LLM agents: how would you know it had stopped working?](https://ivandemurard.com/journal/harnesses-graders-closed-loops) (CC BY 4.0, Ivan de Murard).
