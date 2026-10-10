# End-of-Session Templates

Two documents close every phase. Copy the template, fill every heading, delete nothing.
Both go in `documents/phases/`.

- **Handoff** — written *for the next Claude Code session*, which has read nothing but the
  master plan and its own phase document. Optimize for cold start.
- **Phase review** — written *for the senior designer*, who was not in the session and will
  not read the transcript. Optimize for verification and for deciding what still needs doing.

Rule for both: **no evidence, no claim.** "Fixed B09" is not a statement; a failing run
before and a passing run after is.

---

## Template A — `HANDOFF_PHASE_NN.md`

```markdown
# Handoff — Phase NN: <title>
<!-- vX.Y -->
**Session ended:** <date>  ·  **Next phase:** NN+1 — <title>  ·  **Tree version:** <PROJECT_VERSION>

## 1. What this phase was supposed to do
One paragraph. The review IDs in scope.

## 2. What actually exists now
State of the tree a fresh session will open. New files (path → purpose), renamed/moved
files (old → new), deleted files and why. Anything whose location differs from what the
master plan or an earlier document says.

## 3. Test state (verbatim)
Baseline at session start:
    <paste the summary lines>
At session end:
    <paste the summary lines>
Known failures and skips, each with a reason and a review ID. If a T1 test skips, say why.

## 4. The xfail ledger
| Case / test | Review ID | Why it fails | Which phase flips it |
|---|---|---|---|

## 5. Decisions made this session
| ID | Decision | Why | Evidence |
|---|---|---|---|
Copy each into `CLAUDE.md` (Decisions) as well.

## 6. Gotchas the next session must know
Things that cost time or that look wrong but are correct: environment quirks, hardware
ritual, a workaround and the reason for it, an API that behaves unlike its docstring.

## 7. Open questions carried forward
| Question | Blocks | Who answers |
|---|---|---|

## 8. Start-here checklist for the next session
1. Read `00_MASTER_PLAN.md`, `PHASE_<NN+1>_*.md`, this handoff, `CLAUDE.md`.
2. Unzip <artifact name>; run `tools/run_tests.sh`; confirm it matches §3 above. If not, stop.
3. <phase-specific first step>
```

---

## Template B — `REVIEW_PHASE_NN.md`

```markdown
# Phase NN Review — <title>
<!-- vX.Y -->
**For:** senior designer  ·  **Session date:** <date>  ·  **Reviewer verdict:** ☐ accept ☐ accept with fixes ☐ rework

## 1. Scope
Review IDs in scope, and the one-line goal of the phase.

## 2. Task outcomes
| Task | Review IDs | Status | Evidence |
|---|---|---|---|
| P<NN>-T1 | B04, B05 | Done | `test_b04_editor_preserves_description` fails at <commit/pre-state>, passes after — output §6.1 |
Status is one of: **Done** (fixed + test proving it), **Changed, unverified** (code changed,
no test that fails before and passes after), **Partial**, **Not addressed**, **Deferred**
(with the phase it moved to and why).

## 3. Files changed
| File | Version | Change | Why |
|---|---|---|---|
Flag any file touched that was **not** in the phase document's file list, with the reason.

## 4. Verification performed
Commands run and their results. For firmware: build output, flash procedure, observed
behaviour. For bus work: the capture excerpt. Paste, don't summarise.

## 5. Global passing criteria (master plan §5.2)
| # | Criterion | Met? | Note |
|---|---|---|---|
| 1 | No regressions | | |
| 2 | Task criteria met with evidence | | |
| 3 | Every closed ID has a before/after test | | |
| 4 | smoke_test 9/9 (or formally removed) | | |
| 5 | All decoders validate, before and after round trip | | |
| 6 | Round trip byte-stable | | |
| 7 | Tags bumped, change log written, docs synced, tree zipped | | |
| 8 | xfail ledger exact | | |

## 6. Evidence appendix
Numbered, referenced from §2. Test output, diffs, captures, measurements.

## 7. NOT ADDRESSED — remediation instructions
The most important section. One block per item left open, written so it can be pasted
straight into a Claude Code session with no other context.

### 7.1 <Review ID> — <short title>
**What was expected:** <from the phase document>
**What happened instead:** <observed, with evidence reference>
**Why it was not done:** <ran out of context / blocked on an answer / design changed / missed>
**Risk of leaving it:** <user-visible consequence>
**Instructions to close it:**
1. <concrete step: file, function, change>
2. <concrete step>
**Test to add:** `test_<id>_<behaviour>` — asserts <exact expected output>; must fail
before the change and pass after.
**Passing criteria:** <checkable statements>
**Estimated size:** <small / medium / large>; **suggested phase:** <NN+1 or dedicated>

### 7.2 …

## 8. New findings (not in the original review)
| New ID | Sev | Issue | Where found | Recommended fix | Files |
|---|---|---|---|---|---|
Continue the review's numbering (B29, B30, M11, C13, R10…). Anything found and not fixed
must also appear in §7 with instructions.

## 9. Questions for the senior designer
Decisions the session could not make alone, each with the options considered and the
recommendation.
```

---

## Notes on filling these in

- **"Changed, unverified" is an honest and acceptable status.** Claiming Done without a
  before/after test is not. The reviewer's job is impossible if the two are conflated.
- **Quote the review item** when describing what was expected, so the reviewer does not have
  to hold `ion_i2c_tool_review.md` open alongside.
- **Write §7 as you go**, not at the end — it is the section most likely to be truncated by
  a context squeeze, and it is the section the next session depends on most.
- If the session split mid-phase (master plan §4), the handoff covers `NN-A` only and must
  name the `PHASE_NN-B` document you wrote.
