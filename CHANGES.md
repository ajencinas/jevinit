# CHANGES — review and rework of the ZeroOps / Jev project (2026-10-04)

This document records every change made in the 2026-10-04 rework, why it was made, the evidence behind it, and
the judgement calls along the way. It is written for another model (DeepSeek) to **reflect on and challenge**:
please check the reasoning, not just the diff. Section 10 lists the questions we'd most like a second opinion on.

- Backup of the project before any change (venv excluded): `/home/alfonso/Python/jev_backup_2026-10-04/`
- Full diff: `diff -ru --exclude=jev --exclude=__pycache__ --exclude=.pytest_cache /home/alfonso/Python/jev_backup_2026-10-04 /home/alfonso/Python/jev`
- The project is not a git repository; the backup is the only "before" state.

---

## 1. What the owner asked for

1. "Review the project in detail and see how to improve."
2. "Narrative needs help — still very AI sounding."
3. "I don't want to end up with a recommendation — we can end up with more of a set of considerations and questions
   IT needs to answer and the role of a Jev demo."
4. After the review: "Go ahead with the three" — (1) fix code and labels, re-run all four backends on one corpus
   version; (2) apply the narrative rewrite to the builders and regenerate deck/memo/report/README/pages; (3) redo the
   videos — "and document all the changes in an MD file that DeepSeek can use to reflect."
5. On seeing the first rewrite: "This is not good. The story should be: this is ZeroOps and how it's run today, this
   is what role Jev could play, we have run a demo to illustrate, these were the results, this is the opportunity,
   these are the open questions and next steps in a way that McKinsey could help but being non commercial" and "The
   idea is to make an IT CIO excited about this opportunity in a non commercial way." (→ storyline v2, §5.2)
6. "I also hate how you structure the directory tree — really hard to find the outputs." (→ §8)

## 2. How the work was done

**Review (read-only).** Seven reviewers ran in parallel, each with a fixed scope and a shared brief: code (scripts and
tests), storyline + deck, video scripts, memo/README/web pages, considerations + IT questions (with a review of
`research/`), a claims audit (~70 claims checked against `results/` and `research/`), and an offline data analysis
of the stored decisions (re-running `policy.decide()` on stored answers, threshold sweeps, Wilson and
template-cluster intervals, calibration). The coordinator re-verified every finding that changed the story before
relying on it, and corrected the reviewers when a premise in the shared brief turned out wrong (see 2.1).

**Rework.** Phase 1 (code, labels, re-run) was done by the coordinator alone because every later number depends on it.
Phase 2 (narrative) was split across four parallel agents with disjoint file ownership (deck + memo; README + hub +
research index + pipeline; lab + race + 30s loop + CLIs; the two explainer videos), all reading numbers from one new
file, `results/facts.json`.

### 2.1 Corrections made during the review (worth knowing, because they were nearly published)
- **"The thresholds were tuned on the 56 incidents" — withdrawn.** `zeroops/policy.py` was last modified at 07:47, one
  minute before the earliest results file (07:48). There is no evidence of tuning; what is true is that there is no
  held-out set and that the defaults sit just permissive of observed values.
- **"A severity gate alone produces 0% unsafe" — narrowed.** True only for a gate on the *labelled* severity (the corpus
  confound). On Jev's *own* severity scores it is false: Jev rated the data-corruption incidents (labelled SEV1) as
  minor, and only the rollback-specific checks stopped those rollbacks.
- **"Kev and Laya were scored like Jev" — false.** Their decision files predated a corpus label change; report.py
  reused stored scores. Kev's suspect-component accuracy read 73% but was 84% against current labels.

## 3. Findings that drove the changes (all verified against the data)

| Claim in the old deliverables | What the data showed | What we did |
|---|---|---|
| "Action OK 93%" (headline action metric) | Exact match with our label: **28/56 (50%)**. `ACCEPTABLE_ACTIONS` was added at 08:04, after the first API run (07:48) had been scored; for 6 of 14 templates (24 incidents) Jev is credited only through that list, each time with exactly the action it picked. | Exact match is now the primary metric everywhere; the lenient list is frozen, kept as a secondary column, and its provenance is stated in code and copy. |
| "Calibrated confidence" | Category confidence buckets are not monotonic; ≥0.9 bucket: 32/36 right at mean confidence 0.98; ECE 0.11–0.15. "Page a human" averages 0.77 on safe real incidents and 0.77 on unsafe ones (AUROC ≈ 0.5 among real incidents). | "Calibrated" removed; copy says TypeSafe claims it and our data is too thin to confirm it. |
| "36% automated, 0% unsafe — the routine third" | 56 incidents = 14 templates × 4 near-identical variants (effective n ≈ 14). "0 unsafe" = 0 of 5 unsafe templates (95% upper bound ≈ 43%). Most automated incidents sat just under the 0.90 paging cut-off. | Reported as counts with the template-level bound; fragility shown (AUTO at cut-off 0.80/0.85). |
| "Leads on latency / decision quality" | Laya was as fast or faster on our GPU; Kev-4B beat Jev on exact action (70% vs 50%). | Removed. |
| "Deterministic" | Native vs OpenRouter (same model version) returned different probabilities on every incident and flipped gate outcomes. | Removed; the difference is reported. |
| "$0.0567 per 1,000 incidents" as our measurement | Native API returns no cost; the figure is an estimate at OpenRouter's billed per-token rate. | Labelled as an estimate everywhere. |
| "Cascade cuts LLM billing >90%" | No measurement; the cascade isn't implemented; source is a blog cited in AI-generated research. | Removed. |
| Worked example INC-0001 shown as a clean pass | It cleared `needs_page < 0.90` at 0.88 and `safe_to_autorollback ≥ 0.70` at 0.73; its log named `OrderController.checkout` on payment-svc. | Example kept but shown with its margins (now 0.02 and 0.01 after the re-run); log template fixed. |
| Jev "chooses the action" | It proposed rollback — the first option listed — 16 times vs 4 labelled, including all 4 data-corruption incidents (labelled critical, rated minor by Jev). | Shown as the honest example of option-order risk (options were never shuffled). |

## 4. Phase 1 — code, labels and evaluation (coordinator)

### 4.1 `zeroops/schema.py`
- `parse_answers` now records absent or malformed answers in `Parsed.missing` (non-numeric noul/score, choice not in
  the allowed options, NaN). Values still default to 0.0 for display, but the policy no longer trusts them.
  *Why:* a 200 response with missing answers produced `real_incident = 0` → OBSERVE, i.e. a real incident silently
  ignored, and missing risk/severity defaulted to the most permissive value.
- `ACCEPTABLE_ACTIONS` kept unchanged, with a comment stating its provenance (written after the first run).

### 4.2 `zeroops/policy.py`
- **Fail closed:** any missing gating answer (`real_incident, needs_page, proposed_action, action_risk, severity,
  deploy_correlated, safe_to_autorollback`) → ESCALATE.
- **Order changed:** model proposes `escalate` → ESCALATE, and `needs_page ≥ page_min` → ESCALATE, are now checked
  *before* `real_incident < min` → OBSERVE. *Why:* in the first run Kev-4B proposed "escalate" on four
  data-corruption incidents but gave a low "is this real?" score, so the policy logged them as noise.
- Thresholds unchanged (deliberately — see §9). Removed the "calibrated below" comment (no procedure existed);
  documented that `risk_max = 1.0` lets a *medium*-risk action auto-run.
- New `explain(p, th)`: evaluates every check (not short-circuited) with value, threshold, pass/fail and signed
  margin, so slides/pages render real PASS/FAIL values instead of hand-typed ones.

### 4.3 `zeroops/corpus.py`
- No incident's dependency equals its own service (was 6 of 56, e.g. "payment-svc timing out calling payment-svc").
- `db_saturation` and `data_corruption` now use `db-primary` as the dependency and label it as the suspect
  component (the text names the database; the label named the alerting service). Previously data_corruption said
  "order totals inconsistent in redis-cache".
- Bad-deploy stack trace names a handler in the alerting service (`PaymentController.capture` on payment-svc, …),
  instead of `OrderController.checkout` on every service. Grammar fix "1 account took over" → "taken over".
- New `corpus_fingerprint()` (sha256 of ids, text and labels) stored in every decision record.
- **Deliberately not changed** (documented in the module): the unique per-template LOGS line that names the cause,
  cosmetic-only variants, the severity-3 ⇔ unsafe confound, and the arguable category labels (`db_saturation` =
  "storage" vs "capacity"; `dns_failure` = "network" vs "config"). Changing labels after seeing model outputs is the
  same mistake as the post-hoc acceptable-action list; see §9.

### 4.4 `zeroops/orchestrator.py`, `zeroops/metrics.py`, `zeroops/facts.py` (new)
- Records now carry `corpus_version`, the thresholds used, `attempts`, `pred.missing`, and the full probability
  vectors (`category_probs`, `action_probs`) for later option-order analysis. Backend errors produce
  `decision = ESCALATE (fail closed)` instead of `None`. `correct.real_incident` uses the policy threshold.
- Metrics added: missed incidents (OBSERVE on a real incident) with IDs, escalated non-incidents, AUTO with exact
  action, unsafe automations as a count and per template, Wilson 95% intervals (incl. template-level bound on unsafe
  templates automated), ECE for category confidence, k/n counts for every rate. Rates without a denominator are now
  `None`, not 0 (Laya's old "0% unsafe" with zero automations was meaningless). p95 uses nearest rank.
- `zeroops/facts.py` computes every narrative number (proposed vs labelled actions, lenient-only credit, autos near the
  paging cut-off, threshold sensitivity, data-corruption outcomes and which check stopped each, needs_page separation,
  high-confidence bucket, native-vs-OpenRouter differences, worked examples with `explain()` rows).

### 4.5 `zeroops/adapters.py`
- Pinned model versions by default: `jev-1.13.0` (native) and `typesafe/jev-1.13-20260917` (OpenRouter), overridable via
  `TYPESAFE_MODEL` / `OPENROUTER_JEV_MODEL`. *Why:* the deck told readers to pin versions while the eval used
  the moving `jev-latest` alias. Both endpoints were tested with the pinned ids before the re-run.
- `retries` → `max_attempts` (it always meant total attempts); no sleep after the final attempt; only network errors
  and 429/5xx are retried; non-JSON 200s and 200s without answers are errors. Same empty-answer guard for Laya.
  Kev's port follows `KEV_PORT` (the start script honoured it; the adapter did not). Removed an unused import.

### 4.6 Scripts
- `scripts/run_eval.py`: stamps the corpus fingerprint; `--limit` runs and runs where every call failed go to
  `results/scratch/` and never overwrite good decision files; no longer writes `metrics.json`.
- `scripts/report.py`: the **only** writer of `metrics.json`, `report.md`, `facts.json`, `demo_data.json`; skips decision
  files from another corpus version unless `--allow-stale`; computes everything before writing anything (it used to
  crash on `None` after writing a new `metrics.json` next to stale outputs); cost basis stated per backend; new
  readable `report.md` (k/n counts, which actions each model proposed, missed incidents, template-level bound,
  threshold sensitivity, calibration as "k/n right", column definitions incl. the lenient list's provenance).
- Deleted `results/metrics_api.json` (stale, orphaned; the README's OpenRouter row came from it).

### 4.7 Tests (28 → 51 at the end of phase 1)
- The old `test_parse_answers_tolerates_missing` asserted the silent-drop behaviour; replaced by tests that missing
  and malformed answers are recorded and that the policy escalates on them.
- New: escalate-proposal and high-page beat low real_incident; missing non-gating answer doesn't block; `explain()`
  margins; missed-incident counting and undefined rates; Wilson bounds; corpus invariants (no self-dependency,
  suspects are real components, dependency-side faults blame the dependency, bad-deploy log matches service,
  fingerprint stability); backend error → ESCALATE; records carry version/thresholds; adapter retry/backoff and
  error cases; `parsed_from_pred` round-trip; facts shapes; report generation for a backend that never acts.

### 4.8 Repo hygiene
- `requirements.txt`: added python-pptx and pytest; removed pandas, numpy, scikit-learn (unused); noted the optional
  local backends. Added `.gitignore` (`.env`, venv, caches, `results/scratch/`) and `.env.example` (key names only).

### 4.9 Re-run (all four backends, corpus `0b4839761e06`, pinned models)
Cost: 112 Jev calls (~$0.01) plus 3 pinning test calls; Laya and Kev on the local RTX 5080 (Kev server started with
`scripts/serve_kev.sh`, stopped afterwards). Laya warned: "this checkpoint ships invalid temperatures … Treat confidence
from the affected entries as uncalibrated."

| Backend | Category | Suspect | Exact action | Acceptable | AUTO | Unsafe AUTO | Missed real | Esc. recall | p50 / p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| Jev native — before | 80.4 | 64.3 | 50.0 | 92.9 | 20 | 0 | 0 | 100 | 105 / 169 |
| Jev native — after | 80.4 | 75.0 | 50.0 | 92.9 | 22 | 0 | 0 | 100 | 91 / 128 |
| Jev OpenRouter — before | 78.6 | 62.5 | 50.0 | 92.9 | 21 | 0 | 0 | 100 | 168 / 410 |
| Jev OpenRouter — after | 78.6 | 76.8 | 50.0 | 92.9 | 20 | 0 | 0 | 100 | 134 / 406 |
| Kev-4B — before (older labels) | 71.4 | 73.2 | 69.6 | 85.7 | 8 | 0 | **5** | 80 | 609 / 637 |
| Kev-4B — after | 71.4 | 83.9 | 69.6 | 85.7 | 8 | 0 | 1 | 100 | 589 / 609 |
| Laya — before (older labels) | 42.9 | 57.1 | 21.4 | 35.7 | 0 | 0 | 2 | 100 | 96 / 126 |
| Laya — after | 41.1 | 87.5 | 19.6 | 33.9 | 0 | 0 | 2 | 100 | 91 / 128 |

Reading the deltas: suspect accuracy rose for every backend because the labels were fixed, not because any model
changed. Kev's missed incidents fell from 5 to 1 because of the policy order change (its "escalate" proposals now
reach a person). Jev native's AUTO count moved 20 → 22 through four
flips with two different causes: INC-0002 (AUTO → ESCALATE) and INC-0044 (ESCALATE → AUTO) have **identical text**
in both runs, so they flipped from run-to-run variation of the same model version near a threshold; INC-0016 and
INC-0021 (both ESCALATE → AUTO) are two of the 16 incidents whose text changed (their self-dependency was fixed).
On OpenRouter, INC-0002 and INC-0044 flipped the other way with unchanged text. That run-to-run instability at the
margins is itself evidence for the fragility finding. Latency differences are network/run noise.

New facts after the re-run (from `results/facts.json`): 18 of Jev's 22 AUTO decisions had needs_page 0.73–0.88 vs the
0.90 cut-off; at 0.80 the gate automates 12, at 0.85 17. INC-0001 now clears `needs_page` by 0.02 and
`safe_to_autorollback` by 0.01. All four data-corruption incidents: Jev proposed rollback, rated severity 1.23–1.35
(label 3); stopped by rollback checks (2), risk check (1), action-confidence check (1); INC-0011 cleared
`deploy_correlated` at exactly 0.80. Native vs OpenRouter: probabilities differ on 56/56, 2 gate outcomes flipped.

## 5. Phase 2 — the narrative

### 5.1 What "AI-sounding" meant here, and the voice we replaced it with
The review found the same tells everywhere: "X, not Y" antithesis ("supplement — not replace", "an overlay, not a
replacement", and a voiceover that ended on the banned "Decisions, not strings."); forced triads ("The gap / The fit /
The payoff", "Now / Next / Then"); coined jargon used as a motif ("the decision seam", "platform of record", "the
routine third"); the same taglines recycled across slides, memo and README; a bold kicker under every slide restating
its headline; speaker notes that only repeated the slide title; consultant scaffolding left visible; em-dash chains;
and precision theatre ("$0.0567", "80.4%" on n=56). Underneath the tone was the bigger problem: the copy asserted
more than the evidence supported (§3).

Target voice, applied by every builder: a candid SRE/analyst talking to a CTO. Plain declarative sentences, numbers
with their n and caveat in the same sentence, each idea said once, headlines that are claims the data supports,
limitations stated briefly next to the claim they qualify, speaker notes and voiceover written to be spoken.

### 5.2 Three versions of the storyline (and an over-correction)
- **v0 (original):** a pitch. "Approve a low-cost, reversible pilot…", "automate the routine third", "more autonomy and
  more safety, at once", ending on a "Recommendation and decision" slide.
- **v1 (owner: "I don't want to end up with a recommendation"):** ended on considerations (C1–C12), the questions IT
  must answer (Q1–Q23) and the role of the demo. Executed honestly but **over-corrected**: limitations led almost every
  slide ("whether it is accurate and safe on your incidents is unknown", "these numbers are a best case"), so the
  deck read as a list of reasons not to proceed. The owner's verdict: "This is not good."
- **v2 (owner: "this is ZeroOps and how it's run today, this is what role Jev could play, we have run a demo to
  illustrate, these were the results, this is the opportunity, these are the open questions and next steps in a way
  that McKinsey could help but being non commercial … make an IT CIO excited about this opportunity in a non
  commercial way"):** the current version. Opportunity-forward; each slide leads with what is promising and states the
  honest condition briefly; caveats sit with the results and in "what we learned / what to test next"; next steps are
  three stages with a decision point after each (diagnostic 2–3 weeks; offline replay of closed tickets 3–4 weeks;
  shadow then assist 6–8 weeks) and a modest "where we could help" with no prices, no "engagement", no pitch. The
  evidence rules did not change: numbers from facts.json, exact action match first, no "calibrated", "deterministic",
  "safe" or "proven". Considerations C1–C12 moved to the appendix and `demo/questions.md`.

Lesson worth reflecting on: honesty and enthusiasm are not opposites. v1 fixed the overclaims but let caution set the
tone; v2 keeps every correction and changes the order and emphasis: vision and mechanism first, the demo as an
illustration, the caveats framed as the agenda for a real test.

### 5.3 The considerations and questions document (coordinator)
- `content/questions.template.md` (new): the 12 considerations, 23 questions grouped by owner (SRE/operations,
  ITSM/platform, security, risk & compliance, procurement, finance, leadership), the role of the demo, and six
  extension options with effort. Drafted by a review agent from `research/` and the code, corrected by the
  coordinator (threshold-tuning claim withdrawn; data-corruption "stopped by the severity check" corrected), then
  updated for phase 1 (fail-closed handling, pinned versions and threshold logging are now done, so option A shrank).
- `scripts/build_questions.py` (new) renders it to `demo/questions.md`, filling every demo number from
  `results/facts.json` and the decision logs; unknown or unused placeholders are errors. The hub links it and copies it
  to `demo/docs/`. Added to `run_all.py` after the memo.
- `tests/test_questions.py` (new): all placeholders filled, C1–C12 and Q1–Q23 present in order, key numbers equal
  facts.json, no banned phrases, no "we recommend".

### 5.4 Storyline: `content/claims.json` (agent; rewritten twice)
Final (v2): audience (a CIO), purpose and a governing thought with no numbers, a ZeroOps definition ("the aim of
running routine incidents with no manual work: detected, triaged and resolved automatically, with people on the novel
and the risky"; nothing in `research/` defined it, so this is our wording), five pillars, section labels for the arc,
13 main and 11 appendix titles (claims with `{fields}` filled from facts.json at build time, so no result is typed in),
and three blocks both the deck and memo read: `opportunity_levers` (four, each with hypothesis, "what would need to be
true", "how you'd measure it"), `next_steps` (three stages with duration, condition, scope and decision) and
`where_we_could_help` (five modest items). Banned list grown from 7 to 28 phrases (recycled taglines, "typed,
calibrated", "calibrated confidence", "a different output contract", "supplement… replace" variants, "partner with
us", "engagement"). Previously no script read this file; now the deck and memo do. (v1 had 10+10 titles ending on
considerations, questions and the demo's role.)

### 5.5 Executive deck: `scripts/build_ppt.py` (agent; rewritten twice)
Original 25 slides → v1 21 slides → **v2 25 slides: 13 main, divider, appendix A1–A11.** Main titles as rendered:
1. ZeroOps: taking routine incident decisions off your teams, and where a model like Jev could help
2. A fast decision model could take routine incident calls off your teams, and finding out on your own tickets is cheap
3. Today the tools detect and execute well; the decisions in between still fall to rules and on-call engineers
4. The middle is where incidents wait and automation stalls, and the major platforms are now building for it
5. Jev is built for these calls: fixed questions in, answers with probabilities out, and your code decides
6. Jev could sit at three decision points inside your existing tools, after your rules and before a person
7. To make it concrete, we built a working demo: 56 synthetic incidents, 12 questions, one gate, four models
8. End to end: the gate rolled back a bad deploy on thin margins and stopped a wrong rollback on corrupted data
9. Jev answered in a median 91 ms at about 6 cents per 1,000 incidents, and the gate handled 22 of 56 end to end
10. The mechanism worked end to end; accuracy and margins on real tickets are what to test next
11. Four levers could move routine incidents toward ZeroOps; each is a hypothesis you can test on your own tickets
12. Eight questions would tell you whether the opportunity is real for you; each has an owner
13. Three short stages would show whether this works on your tickets, with a decision after each

Appendix: A1 all 23 questions by owner · A2 considerations C1–C12 (titles read from the questions document) · A3
question set · A4 the gate and why each escalation happened · A5 method and corpus · A6 full results and confidence ·
A7 vendor facts · A8 risks, security, compliance · A9 component map · A10 ways to extend the demo, by stage · A11
sources.

Kept from v1 and still true: every result read from facts.json/metrics.json; the two worked examples (INC-0001,
INC-0011) with gate rows from `explain()` (real PASS/FAIL, signed margins, amber within 0.05, "exactly at limit");
exact action match shown before the lenient figure, with the lenient list's provenance footnoted; cost only as an
estimate; speaker notes as spoken talk tracks; layout fixes (theme drop shadows, hanging-indent bullets, alignment,
panel sizing, label collisions, table overflow); the memo block that overwrote the memo on every build removed.
Cut from the original: the business-case slide (unsupported "cuts LLM billing >90%", "real SOC 2 / EU AI Act evidence
trail"), the recommendation slide, the landscape/patterns slides and the A13 model comparison table (vendor latency
ranges our own runs contradicted). Vendor momentum on slide 4 is labelled Independent (PagerDuty SRE Agent GA,
Datadog Bits AI SRE GA, Dynatrace autonomous SRE agent announced, every major cloud ships one; source
research/independent-review-claude.md). The coordinator reviewed slides 2, 5, 9, 11 and 13 rendered.

### 5.6 One-page memo: `scripts/build_memo.py` (new; rewritten twice)
Generated from facts.json (numbers) and claims.json (levers, stages). ~510 words, same arc as the deck: how incidents
run today · the role Jev could play · what our demo showed (encouraging results first, INC-0001 and INC-0011, then the
honest condition: synthetic incidents, exact match half the time, rollback 16 vs 4, 18 of 22 near the paging cut-off)
· the opportunity (four levers) · open questions (Q1, Q8, Q10, Q12, Q17, Q23 with owners) · next steps and how we could
help (three stages with their decision questions; modest help).
`tests/test_memo.py`: storyline has the banned phrases and 13+11 titles and no typed results; the memo on disk equals
`build_memo(facts)`; key numbers equal facts.json and follow when facts change; stage names and durations; no banned
phrases, "calibrated", "deterministic", "recommend", "proven" or "routine third" in memo or deck; 25 slides.

#### Before / after (voice)
| Before (v0) | After (v2) |
|---|---|
| "Add a typed decision layer to your existing tools: automate the routine third, escalate the rest" | "A fast decision model could take routine incident calls off your teams, and finding out on your own tickets is cheap" |
| "Measured on 56 incidents: Jev leads on decision quality, automation, and latency — with zero unsafe actions" | "Jev answered in a median 91 ms at about 6 cents per 1,000 incidents, and the gate handled 22 of 56 end to end" + "The mechanism worked end to end; accuracy and margins on real tickets are what to test next" |
| "This is not a smaller LLM — it is a different output contract" | "Jev is built for these calls: fixed questions in, answers with probabilities out, and your code decides" |
| "Benefits — business case: … the cascade cuts LLM billing >90%" | "Four levers could move routine incidents toward ZeroOps; each is a hypothesis you can test on your own tickets" |
| Notes: "Walkthrough: one incident, twelve decisions, one gate." | Notes: a spoken walk through INC-0001's close calls and INC-0011's wrong rollback that the gate stopped |
| Memo: "**The answer.** … automates the routine ~36% of incidents with 0% unsafe actions" | Memo: "… the gate handled 22 of 56 end to end … its action matched our label half the time …" |
| "Start in overlay shadow mode; automate only reversible, high-confidence actions; expand from there" | "Three short stages would show whether this works on your tickets, with a decision after each" + "Where we could help" |

## 6. Phase 2 — README, hub, research index, pipeline, pages, loop and CLIs

### 6.1 README.md (rewritten; agent)
Opens with what was tested and what the results can't show; recommends neither buying nor piloting. A results block
between `<!-- results:start -->` and `<!-- results:end -->` is generated by `build_hub.py` from facts.json (three
headline findings with n and caveat; a four-backend table with model ids, exact and acceptable action, AUTO, unsafe
scenario types with the 95% bound, missed incidents, p50/p95, cost with its basis; a "before quoting" caveat list).
Hand-written sections contain no result numbers: repo map (adds facts.py, build_memo.py, build_hub.py,
build_questions.py, .env.example, demo/docs/; removes metrics_api.json), offline vs paid run instructions with costs,
machine-specific paths (Node 22 now at `/media/alfonso/shared/jev_local/node22/bin`), a bold warning never to serve
the project root (`.env`), "Maintaining this repo" (facts.json single source, report.py only writer, corpus
fingerprint, pinned models, fail-closed policy, tests, generated files), writing rules, known limitations.

### 6.2 `scripts/build_hub.py` (new) → `demo/index.html`, `demo/docs/`
The hub was hand-written and wrong ("17 slides" for a 25-slide deck, "2:39" for a 2:26 video, "every number computed
from metrics.json", "the phased recommendation", hardcoded race timings). It is now generated: headline numbers from
facts.json, slide counts/appendix split from the pptx, durations from ffprobe, race details from the trace; any
deliverable older than the newest decision log gets a visible "may be out of date" note; the build fails if a banned
phrase reaches the page or the README block (whole-phrase matching). Linked documents are copied into `demo/docs/`, so
`python -m http.server --directory demo` serves everything without exposing `.env`. Works at phone width.

### 6.3 `scripts/run_all.py` (rewritten)
Order: API → Laya → Kev → report → ppt → memo → questions → lab → demo → race → (videos) → hub. Flags: `--skip-api`,
`--race-live` (paid, tiny), `--videos` (paid TTS + HyperFrames renders, pinned `hyperframes@0.8.114`), `--dry-run`.
`run_eval` exit 2 (no backends) is a note, not an abort; a Kev server started by the script is always stopped in a
`finally`; scripts and npx are checked before any paid step.

### 6.4 `research/`
`research/README.md` rewritten: per-file provenance (Claude / Gemini-OpenAI model-generated research, AI-assisted
synthesis), states that `independent-review-claude-source.md` is byte-identical to `independent-review-claude.md`
(checked with cmp/MD5; kept, not deleted), and lists weak or wrong sources (blog-sourced prices and "$20–25k",
">90% LLM bill", the "0.90 confidence = 90% accuracy" claim, EU AI Act scope, the Cribl comparator, unsourced "200+"
and "$1M/yr", "~2k tokens"). `research/landscape-synthesis.md`: one line, the broken citation in §13.

### 6.5 Threshold Lab (`scripts/build_lab.py` → `demo/lab/`, `results/lab_data.json`)
New copy and labels (exact vs acceptable action, missed incidents tile, "what this page can't show"). Bugs fixed:
Jev native was shown at $0 (now the labelled estimate), calibration lumped everything below 0.5 into one bin (now
0.1-wide bins, same as metrics.py), "median" took the upper median. The flat action-confidence chart was replaced by a
page-cut-off sweep (acted alone / action other than our label / labelled unsafe). The JS gate is a rule table in the
new policy order; `tests/test_lab_parity.py` ports it to Python and compares with `policy.decide` on all 224 recorded
answers, every slider position, 150 random threshold sets and 3,000 boundary cases, runs the page's actual JS through
node, and was mutation-checked (old rule order → 2,413 mismatches). A "Try this" note, computed from the logs: with
rollback safety at 0.40, 2 of the 4 data-corruption incidents are rolled back automatically.

### 6.6 "Race" page → "One incident, two kinds of output" (`scripts/build_race.py` → `demo/race/`)
Reframed from a Jev-vs-chat race (n=1, both models gave the same answers) to a side-by-side of typed answers with
probabilities and gate margins vs a chat model's JSON; n=1 caveat stated; fake client-side "streaming" removed; the
page stamps the recorded time from the trace, not the viewer's clock; default build is offline from
`results/race_trace.json`; `--live` re-records and writes only if both calls succeed; unknown `--incident` is an error.
Output tokens described accurately (≈484 reported, not billed). One live run (INC-0001's text had changed): ≈$0.00026.

### 6.7 30-second dashboard loop (`scripts/build_demo.py` → `demo/hf-demo/`, `demo/zeroops-jev.mp4`)
Now silent (narration and `assets/vo.mp3` removed; `demo/vo_script.txt` is a note). Five generated captions and
metric cards from the data files; gate rows from `policy.explain`/`decide` with "close" badges on the 0.02 and 0.01
margins. HyperFrames `check` 0 errors/warnings; rendered 30.5 s 1920×1080; stale frames replaced in `demo/frames/`;
`lab_preview.png` and `race_preview.png` regenerated with headless Chrome.

### 6.8 CLIs
`scripts/demo_cli.py`: panel title follows the backend (Kev was labelled Jev), `--live` uses each backend's own adapter
(was silently OpenRouter for Kev), honest cost labels, gate rows from `policy.explain`, unused imports removed.
`scripts/smoke_api.py`: validates the real 12-question schema (was a separate 4-question one), pinned adapters,
handles non-JSON 200s and missing keys; tested offline with mocked HTTP; not run (paid), so `results/smoke_api.json`
is still the old 4-question output.

## 7. Phase 3 — the videos

### 7.1 Overall explainer (`scripts/build_explainer.py`; rewritten twice)
Pipeline kept (VO per segment → ElevenLabs TTS → segment durations → HyperFrames timing → render) and hardened:
a per-segment TTS cache (only changed text is re-voiced), `--dry-run`, a copy check that fails the build on banned
phrases, "calibrated", "deterministic", "proven", "engagement", spaced dashes or digits in the voiceover, number-to-
speech helpers so every spoken number comes from facts.json, and on-screen reveals timed to the phrase being spoken.
Gate rows come from INC-0001's `checks` (the old hardcoded "PASS" and "ground truth ✓" are gone).
Final (v2) beats: ZeroOps and today's flow (Detect → Correlate → Decide → Act → Record, "Decide" highlighted) → the
judgment calls in the middle and vendor momentum (Independent) → the role Jev could play (three decision points) →
how it answers → INC-0001 (rolled back; two close checks stated) → what the demo showed, positive first (≈91 ms, ≈6
cents per 1,000 estimated, 22 of 56 end to end, none of the 20 unsafe automated, the gate stopped all four
data-corruption rollbacks; then "accuracy on real tickets still needs testing: its action matched our label half the
time") → the opportunity (routing, triage, reversible fixes behind a gate; inference close to free, so value rests on
accuracy on your tickets) → open questions and the three stages, closing "We'd be glad to help."
Runtime 2:44 (163.6 s; was 2:26). TTS: v1 8 segments (2,311 characters); v2 re-voiced 5 changed segments (1,673
characters), 3 reused from cache. Checked: HyperFrames check 0 errors/warnings, 7 frames reviewed against facts.json,
a faster-whisper transcript of the new segments matched the script. Known nit: segment 3's voiceover is v1 text over a
new screen (kept to avoid re-voicing; it still fits).

### 7.2 "How Jev works" deep-dive (`scripts/build_howitworks.py`; rewritten once)
Beats: why not a chat model (the recorded comparison: the chat model gave the same 5 answers, with no per-answer
probability) → the call → three question types with INC-0001's real values → probabilities, with the six **measured**
confidence bands and ECE (the old version drew invented 60/90/96% calibration bars) → the gate in order → the
INC-0001 close call with a strip of all 22 automated incidents' page scores and the 0.90/0.80 cut-offs → rollback as
option one (16 vs 4) with INC-0011's gate rows → limits (no held-out set, 22 → 12 at a 0.80 cut-off, native vs
OpenRouter differ on 56/56 with 2 flips, planted text). Never calls Jev calibrated or deterministic. Runtime 2:42
(162.5 s). TTS 9 segments, 2,420 characters. Pinned `hyperframes@0.8.114` for both projects.

### 7.3 30-second dashboard loop
See §6.7 (made silent). After review the coordinator put an installed monospace font first in its stacks (the
incident text had fallen back to a proportional font), renamed the gate label "action is one the gate may run" to
"action is on the auto-approved list" (also in the lab), and re-rendered (30.5 s).

### 7.4 Cost of paid calls in this rework
Jev API: 112 evaluation calls + 3 pinning tests + 1 race call (≈1 cent). OpenRouter chat (race): 1 call (≈$0.0002).
ElevenLabs: 22 segments, 6,404 characters across both videos and both explainer versions (≈$1.5–2 depending on plan).

## 8. Where everything lives now (directory restructure)

Owner: "I hate how you structure the directory tree — really hard to find the outputs." Outputs had been spread across
`demo/` (mixed with video source projects), `results/` and preview folders. Now every output is in one folder,
numbered in reading order, with a generated index; sources and raw data each have their own folder.

```
deliverables/                         ← START HERE (serve this folder only; never the root, which holds .env)
  README.md                           generated index: each file, what it is, how to open, size/length, built, up to date?
  index.html                          hub page
  1_ZeroOps-Jev_deck.pptx  (+ .pdf)   13 main slides + 11-slide appendix, speaker notes
  2_ZeroOps-Jev_memo.md               one-page memo
  3_open-questions-and-next-steps.md  considerations C1–C12, questions Q1–Q23 by owner, staged next steps
  4_explainer.mp4                     narrated, 2:43
  5_how-jev-works.mp4                 narrated, 2:42
  6_dashboard-loop.mp4                silent, 0:30
  7_results-report.md                 every results table with definitions
  lab/  one-incident/  dashboard/     interactive pages
  previews/{deck,video,pages}/        slide PNGs, video frames, page screenshots
  docs/research/                      research files linked from the hub
content/    storyline (claims.json) and the questions template      research/  background research (inputs)
results/    raw run data (decision logs, metrics, facts, traces)    video/     HyperFrames source projects
zeroops/    Python package (incl. paths.py)                          scripts/   builders and runners
tests/      92 tests                                                 third_party/, jev/ (venv)
```

| Old | New |
|---|---|
| demo/ZeroOps-JEV.pptx, demo/ppt_preview/ZeroOps-JEV.pdf | deliverables/1_ZeroOps-Jev_deck.pptx, 1_ZeroOps-Jev_deck.pdf |
| demo/exec-memo.md | deliverables/2_ZeroOps-Jev_memo.md |
| demo/questions.md | deliverables/3_open-questions-and-next-steps.md |
| demo/zeroops-explainer.mp4, zeroops-how-jev-works.mp4, zeroops-jev.mp4 | deliverables/4_explainer.mp4, 5_how-jev-works.mp4, 6_dashboard-loop.mp4 |
| results/report.md | deliverables/7_results-report.md |
| demo/index.html, demo/docs/ | deliverables/index.html, deliverables/docs/ |
| demo/lab/, demo/race/ | deliverables/lab/, deliverables/one-incident/ |
| demo/ppt_preview/*.png, demo/ex_frames/, demo/frames/, demo/*_preview.png | deliverables/previews/deck/, video/, pages/ |
| demo/explainer/, demo/how-it-works/, demo/hf-demo/ | video/explainer/, video/how-it-works/, video/dashboard-loop/ |
| demo/vo_script.txt, empty data/ | removed |

How it is enforced: `zeroops/paths.py` holds every path constant and all scripts and tests import from it;
`scripts/export_deck.py` (new) writes the deck PDF and slide PNGs; `build_hub.py` also writes `deliverables/README.md`
with staleness flags; `build_demo.py` also writes `deliverables/dashboard/`; `tests/test_layout.py` (13 tests) fails on
any literal `demo/` path in code, any broken relative link in the three HTML pages, or a numbered deliverable missing
from the index. Paths in earlier sections of this document are historical; this table maps them.


## 9. Judgement calls (and the alternatives we rejected)

1. **The policy order change alters the system under evaluation.** Escalate-proposal and high needs_page now win over
   "not an incident". This is a design change, not just a bug fix: it trades possible extra pages on flukes (none
   came from the new order in this run: 0 escalated non-incidents for Jev and Kev; Laya's 4 are planned-maintenance
   incidents where it proposed "drain", which is not auto-approved, a path the old order also escalated) for never
   discarding a model's own request for a human.
   Alternative rejected: keep the old order and only report missed incidents. We judged a policy that can log an
   "escalate" as noise to be wrong for any operations context.
2. **Thresholds left unchanged.** Tuning them on 56 synthetic incidents would repeat the post-hoc problem we found.
   We report sensitivity instead (AUTO at page cut-off 0.80 / 0.85 / 0.95).
3. **The lenient acceptable-action list was frozen, not edited.** Some alternatives are weak on SRE grounds (scale_up for a
   memory leak; scale_up for a DB pool exhausted by an analytics query), but pruning them now — after seeing that Jev
   picked them — is post-hoc in the other direction. We demoted the metric and disclosed its provenance. The right
   fix is a blind re-definition by an SRE before the next run.
4. **Arguable category labels were not relabelled.** Jev's high-confidence category misses fall on `db_saturation`, where
   our label ("storage") is arguable against "capacity" (whose description includes "connections"). Relabelling would
   raise Jev's category score to ~88% and would be another change made after seeing outputs. We disclose it instead.
5. **Clear label bugs were fixed even though they changed scores.** Self-dependencies and suspect labels pointing at the
   wrong component are errors independent of any model's output, so they were fixed and every backend re-run on the
   same version.
6. **Models pinned.** The narrative's own advice ("pin the version") now applies to the eval itself.
7. **The 30-second narrated loop was made silent** (decided with the video reviewer): narration over a dashboard loop was
   the most advert-like artefact, and its script ended on a banned slogan.
8. **Next steps without a sales pitch.** v1 had no recommendation at all; v2 (owner's direction) ends with open
   questions and a staged path with a decision point after each stage, plus a modest "where we could help". We kept the
   word "recommend" out of the deck and memo (a test enforces it), quote no prices or engagement terms, and point out
   that the harness runs any model, so the choice of tool stays with the client.
9. **Research documents were not rewritten or deleted.** They are model-generated inputs; we fixed the index, the broken
   citation, and labelled provenance and weak sources. The two byte-identical independent-review files were kept (the
   index now says so) rather than deleted.

## 10. Questions for the reviewing model (please challenge these)

1. Is the policy order change (§9.1) right? Should a high `needs_page` on something the model thinks is *not* real
   page a human, or does that invite alert fatigue in production?
2. Is reporting the unsafe-automation bound at the template level (0 of 5 → upper bound ~43%) the right unit, or does
   it understate the evidence from 20 incidents? We chose it because variants of a template get near-identical answers.
3. Was freezing the post-hoc acceptable-action list (rather than removing it) the honest choice?
4. v1 over-corrected (limitations led every slide; the owner rejected it). Does v2 get the balance right for a CIO:
   excited by the opportunity, yet not misled? Point to any sentence that now overstates the evidence, or any caveat
   that is buried.
5. "Page a human" carries no signal among real incidents on this corpus. Is that a model property, a question-wording
   problem ("independent of any automated action"), or a corpus artefact? What experiment would separate them?
6. Rollback proposed 16× vs 4 labelled, rollback listed first, options never shuffled: what is the cleanest test
   (shuffle order and repeat; rename options; reverse order) and how many runs would it need?
7. Which of the 23 IT questions would you cut or add?
8. Anything in the numbers in §4.9 or the narrative that you can't reproduce from `results/decisions_*.jsonl`?

## 11. Open issues / not done

- The corpus is still easy and small (14 templates, one telltale log line each, severity ⇔ unsafe confound). The v2
  plan is in the review notes: 80–150 distinct scenarios, conflicting signals, injection cases, option-order shuffle,
  held-out threshold selection, repeat runs, labelled decision questions, blind acceptable-action sets.
- `blast_radius` and `customer_impact` are asked but not used by the gate (disclosed in the narrative as a gate limitation).
- `risk_max = 1.0` allows "medium" risk actions to auto-run (documented, unchanged).
- Laya's checkpoint warns its confidences are uncalibrated; Kev runs with CUDA graphs and prefix cache off (16 GB card),
  so its latency is not representative of a tuned deployment.
- Local paths are machine-specific (`/media/alfonso/shared/jev_local/…` for Kev, Laya artefacts and Node 22).
- `.env` sits in the project root; it is now git-ignored, but any static server rooted at the project would expose it.

## 12. How to verify

```bash
./jev/bin/python -m pytest tests -q                 # offline; all should pass
./jev/bin/python scripts/report.py                  # rebuilds metrics/facts/demo_data + the results report (no calls)
./jev/bin/python scripts/run_all.py --skip-api --skip-local   # rebuilds every offline deliverable (no paid calls)
cat deliverables/README.md                          # what each output is and whether it is up to date
cat deliverables/7_results-report.md               # the numbers in §4.9
./jev/bin/python -c "import json;print(json.dumps(json.load(open('results/facts.json'))['jev'],indent=1)[:3000])"
diff -ru --exclude=jev --exclude=__pycache__ --exclude=.pytest_cache ../jev_backup_2026-10-04 . | less
```
Re-running the backends costs ~1 cent (Jev) and needs the local GPU artefacts for Kev/Laya:
`./jev/bin/python scripts/run_eval.py --backends api`, then `LAYA_MODEL=typed-decisions ... --backends local --only laya_local`,
then `scripts/serve_kev.sh` and `--only kev`, then `scripts/stop_kev.sh` and `scripts/report.py`.


---

# PART 2 — second rework, same day: sector-neutral storyline, three-bucket layout, F5 thread (2026-10-04, later)

This part records the second round of changes, made after the owner reviewed the Part 1 result. Same rules as Part 1:
every narrative number still comes from `work/results/facts.json`; the backup at
`/home/alfonso/Python/jev_backup_2026-10-04/` predates Part 1, not this round.

## 13. What the owner asked for this time

1. "This file is better — ZeroOps for Utility Operations (in Downloads)" — a deck generated by the Kimi online app.
   Adopt its storyline.
2. "I don't want focus on utilities — I want focus on IT operations broadly." The Kimi deck was utility-flavoured; the
   storyline was to be kept, the sector framing removed.
3. "Reorganize file structure — super unclear what is input, output, process." (Approved shape: three top-level buckets
   `inputs/`, `work/`, `outputs/`; a deeper `src/` move was offered and rejected.)
4. "Could we do some of this about network monitoring a bit more — one of the applications should be F5 network
   monitoring."
5. "Make this a bit more graphical on what Jev does — showing a screen and how the end to end would work."
6. "Recreate the whole thing and test"; rebuild the videos without the utility angle; upload to Google Drive via rclone.

## 14. Directory layout: three buckets

| Before (Part 1) | Now |
|---|---|
| content/ (claims.json, questions template) | inputs/ |
| research/ | inputs/research/ |
| — | inputs/reference/ (the Kimi-online deck, kept as the storyline source) |
| results/ | work/results/ |
| video/ | work/video/ |
| deliverables/ | outputs/ |

`zeroops/paths.py` is still the single place that holds paths; every script and test imports from it. Path strings in
scripts, tests and docs were rewritten mechanically and then checked by the test suite (`tests/test_layout.py` still
fails on any `demo/` literal). `.gitignore` now covers `work/results/scratch/`. After the move, before any narrative
change, the full offline rebuild and all 92 tests were re-run green.

## 15. The storyline: Kimi-online wording, sector-neutral

- The Kimi deck was copied to `inputs/reference/ZeroOps for IT Operations (Kimi online, 2026-10-04).pptx` and its text
  extracted; the owner judged its storyline better than Part 1's v2.
- `inputs/claims.json` rewritten around it: 16 main + 11 appendix slide titles (Kimi wording, `{fields}` for every
  number), new section labels (ZeroOps for IT operations / story on a page / the industry / the gap / what a decision
  model adds / the evidence / the value / the path), Kimi-worded `opportunity_levers`, `next_steps` (Stage 2's decision
  is now "Does it beat what runs today, by enough to matter?") and `where_we_could_help` ("Where outside help fits",
  with NIS2 / DORA / EU AI Act as the compliance hooks). No utility wording anywhere; a test still bans the old phrases.
- The deck's industry figures (Microsoft's 1,300+ agents, PagerDuty's 175-minute/$794k study, Splunk/Oxford Economics
  $200M downtime, Gartner 70%-by-2029 vs 28% success, 2026 SRE Report 34% toil, Resolve AI's $125M round,
  DigitalOcean/Traversal's 36k hours) come from the Kimi deck, **not** from this repo's original research. They are
  hardcoded in `build_ppt.py` slides 3–4 with per-figure labels (vendor-reported / vendor-commissioned / secondary
  coverage) and traced to a new provenance note, `inputs/research/industry-evidence-kimi-online.md`, which states
  plainly that they were **not re-verified** against primary sources. This follows the repo's existing precedent for
  labelled vendor claims; it is the weakest evidentiary link in the deck and is called out as such on the slides
  themselves.

## 16. The deck: 27 slides, no divider, a real screenshot

`scripts/build_ppt.py` rewritten end to end: 16 main slides + appendix A1–A11, no divider slide, speaker notes on every
slide (spoken talk tracks, not repeated titles).

- **Slide 9 is the graphical slide the owner asked for.** Left: the end-to-end flow in five boxes (alert from F5 /
  Datadog / ServiceNow → 12 typed questions in one call → gate in owned code → AUTO / ESCALATE / OBSERVE → logged to
  the record). Right: a real screenshot of the one-incident dashboard, showing the alert, the 12 answers with their
  probabilities, each gate check with its margin, and the outcome.
- The screenshot was the fiddly part. The dashboard page is a GSAP animation that starts paused at time 0, so a naive
  headless-chromium capture got an empty page. `build_demo.py` now honours a `?end` query parameter that seeks the
  timeline to its final frame; `build_ppt.py`'s new `dashboard_shot()` captures that URL with headless chromium to
  `outputs/previews/pages/dashboard.png` (reused while newer than the page; a drawn placeholder if no chromium exists).
- The **F5 / network-monitoring thread** runs through: slide 1's flow strip, slide 5 (Detect box lists F5 telemetry; a
  note that network monitoring raises the same four calls at higher volume — pool member down, certificate expiring on
  a VIP, HA failover), slide 10 (the corpus's cert_expiry / dns_failure / network_partition fault types are "the same
  shapes an F5 BIG-IP reports"), and appendix A9's component table (new row: network monitoring — F5, Zabbix,
  SolarWinds — "the same four calls at higher volume: triage and routing first").
- Layout fixes found by reading the rendered PNGs: slide 3's bullet block overlapped the source line (block spacing
  tightened, one bullet trimmed); title strips, table row heights and stat-card sizes re-checked on slides 1–16 and
  A1, A4, A9, A11.

## 17. Everything else that moved to the new storyline

- **Memo** (`scripts/build_memo.py`): sector-neutral; headings now "Why now, and the gap / What a decision model adds /
  What our demo showed / The value / Open questions / The path, and where outside help fits". Exactly 560 words of
  body, the test ceiling — any future addition needs a matching trim.
- **Questions document** (`inputs/questions.template.md`): intro, stage text and the help paragraph de-utilitied
  (incident surges, out-of-hours pages, NIS2 / DORA / EU AI Act).
- **Hub** (`scripts/build_hub.py`) and **README.md**: new copy; the README's "What's here" is now a map of the three
  buckets.
- **Explainer voiceover** (`scripts/build_explainer.py`): utility references removed; s1 now says the same flow "runs
  in network monitoring, at even higher volume: a pool member down on an F five, a certificate expiring on a VIP, a
  failover at three in the morning" (spelled for TTS — the copy lint fails the build on digits in the VO, which is how
  "F 5" got caught). Re-rendered: 3:05 (185.4 s; s1, s2, s7, s8 re-voiced, s3–s6 reused from the TTS cache). The
  deep-dive video needed no copy changes (2:42, all segments cached); the silent dashboard loop re-rendered at 30.5 s.
  Spot-checked frames at 8 s (title card) and 150 s (the three levers) of the explainer: sector-neutral, no utility
  wording.
- **Tests**: `tests/test_memo.py` updated (16+11 slides, no divider, new memo headings, the handled-count phrase moved
  to slide 12); everything else passed unchanged after the path rewrite.

## 18. Judgement calls this round

1. **Unverified industry figures were adopted with labels rather than dropped or silently trusted.** The owner prefers
   the Kimi deck's storyline, which leans on those numbers. Each figure carries its provenance on the slide; the
   research note says they were not re-checked; a verifying pass is a listed next step.
2. **The Kimi deck's utility framing was dropped, its structure kept.** Sections, titles and the three-stage path are
   near-verbatim; every sector reference was generalised to IT operations.
3. **A screenshot of the real dashboard, not a redrawn mock.** A redrawn fake would drift from the real page; the
   `?end` capture keeps the slide honest (the same page a viewer can open from the hub).
4. **Drive layout unchanged remotely.** Uploads still go to `gdrive:ZeroOps-Jev/deliverables` even though the local
   folder is now `outputs/` — renaming the remote folder was left to the owner.

## 19. Upload and how to verify this round

Uploaded with `rclone copy outputs gdrive:ZeroOps-Jev/deliverables --checksum`; verified with `rclone lsl` (deck, memo,
questions, report, both narrated videos and the hub stamped 2026-10-04 18:07–18:11; the dashboard loop skipped because
the re-render is bit-identical — the only source change, the `?end` snippet, does not alter any frame).

```bash
./jev/bin/python -m pytest tests -q                              # 92 passed
./jev/bin/python scripts/run_all.py --skip-api --skip-local      # offline rebuild of every deliverable
ls outputs/previews/deck/                                        # 27 rendered slides, incl. s-09 with the dashboard shot
cat inputs/research/industry-evidence-kimi-online.md             # provenance + the not-re-verified warning
```
