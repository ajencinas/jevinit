# Considerations, open questions, and the role of the Jev demo

This is the reference behind the last part of the ZeroOps / Jev story. The deck and memo make the case that a
typed decision model like TypeSafe's Jev could take routine incident decisions off IT teams, in application
incidents and network monitoring alike; this document sets out what decides whether that holds for a given
incident estate (section 1), the questions the owners in IT would need to answer (section 2), and what the demo
shows, what it cannot, and a staged way to find out on your own data (section 3).

Labels: **Our measurement** (results/, zeroops/), **Vendor claim**, **Independent**, **Judgement**.
Every demo figure below is filled in from `results/facts.json` by `scripts/build_questions.py` (corpus version
`{{corpus_version}}`; {{n}} synthetic incidents from {{n_templates}} templates). Edit the wording in
`content/questions.template.md`, never the numbers. The C- and Q- numbers are used by the deck, memo and videos.

---

## 1. Considerations

### C1. It fits text classification at volume, and little else
Jev answers multiple-choice, rating-scale and yes/no questions about a block of text, with a probability
attached. That matches first-line triage decisions: category, owning group, "is this a duplicate?",
"is there enough information to route?", where the ticket history already supplies the labels.
TypeSafe's own limitations page says it does no arithmetic or reliable counting, reads dates as text and
generates no text, so anomaly detection, threshold maths, time-window correlation, summaries and
postmortems stay with other tools.
*Source:* research/independent-review-claude.md, "Documented failure modes" and component table rows 2, 6
and 10; research/landscape-synthesis.md §14. *Label:* Vendor claim (limits), Independent (fit).

### C2. The value is the gap to what you already run
A routing model is worth adding only if today's routing is measurably poor and nothing already licensed
fixes it. ServiceNow Predictive Intelligence, Now Assist and the 2026 AIOps "AI specialists", PagerDuty
Event Orchestration and AIOps, or a plain classifier trained on ticket history may already do the job.
The independent review's bar is that Jev must match an in-house classifier or a structured-output LLM on
accuracy while being cheaper, faster or easier to maintain.
*Source:* independent-review-claude.md, "Comparative baseline" and "Overlap check";
build-vs-buy-gemini-openai.txt, "Foundation and measurement". *Label:* Independent, Judgement.

### C3. Results depend on what the ticket says at the moment of decision
The demo's incidents are short templates ({{words_min}}-{{words_max}} words, median {{words_median}}) with
textbook cues such as "x509: certificate has expired"; the {{n}} incidents reduce to {{n_templates}} distinct
texts once service names and numbers are normalised, which is why root cause scored {{rc_jev_pct}} for Jev and
{{rc_kev_pct}} for Kev-4B. Real tickets arrive with empty short descriptions, pasted stack traces and forwarded
email threads, and TypeSafe documents that accuracy falls as irrelevant text grows ("context rot"). The number
of options matters as well: Cribl found Jev misclassified 2-3 times more often than a purpose-built classifier
on a 28-way log task.
*Source:* zeroops/corpus.py; deliverables/7_results-report.md; independent-review-claude.md, "Key Findings" 3 and
"Risks and red flags". *Label:* Our measurement, Vendor claim, Independent.

### C4. Thresholds and calibration have to come from your own data
On our incidents the category confidence does not track accuracy reliably (by confidence band:
{{calib_list}}; expected calibration error {{ece}}). Answers given at 0.9 or above were right {{top_k}} of
{{top_n}} times at a mean stated confidence of {{top_conf}}. The policy thresholds were set by hand before the
first run and have never been checked on held-out data. Automation is very sensitive to them: {{near_k}} of the
{{autos}} incidents the gate automated had a "page a human" probability between {{near_min}} and {{near_max}},
just under the {{page_cutoff}} cut-off; at 0.80 the gate would have automated {{autos_080}}, at 0.85
{{autos_085}}. Pydantic describes the confidence as "a margin, not a probability that the answer is right".
*Source:* deliverables/7_results-report.md (calibration, sensitivity); zeroops/policy.py; independent-review-claude.md,
"Build-vs-buy considerations" (Risk). *Label:* Our measurement, Independent.

### C5. Question wording and option order shape the answer
The model answers the question as written: our needs_page question asks about paging "independent of any
automated action", and the gate automated incidents where that probability was as high as
{{autos_max_page}}. Jev proposed "{{first_opt}}", the first option in the list, {{first_prop}} times where our
labels called for it {{first_lab}} times, including {{dc_rollback_phrase}} data-corruption incidents, and it never chose {{never_chosen}}. That pattern fits the documented first-option
bias, but the demo never shuffled the options, so it cannot separate bias from question design.
*Source:* zeroops/schema.py (action list order); results/decisions_jev_native.jsonl;
independent-review-claude.md, "Documented failure modes". *Label:* Our measurement, Vendor claim.

### C6. Anyone who can write into a ticket can lean on the answer
Ticket descriptions, customer emails, third-party alert payloads and application log lines are all
attacker-influenceable. Check Point's strongest attacker broke Jev in 25 of 27 runs, and Octomind moved a
"block `rm -rf ~/.ssh`" probability from 0.76 to 0.48 with one planted field; an arXiv study found much
lower success in agent tool-use settings (1.8% rising to 3.5%), so severity depends on the task. The
published mitigations are architectural: keep untrusted text out of questions that gate actions, and keep
action authority outside the model.
*Source:* independent-review-claude.md, "Key Findings" 4 and "Risks and red flags";
composable-stack-and-compliance-gemini-openai.txt, "The Fallacy of Prompt Injection Immunity".
*Label:* Independent.

### C7. The gate is only as good as what it checks and how it fails
For restart, scale-up and config patch the demo's gate checks only action confidence, risk score and
severity; blast radius and customer impact are asked and then ignored, and the suspected component was
right {{suspect_pct}} of the time, so an action could land on the wrong service. Failure behaviour matters
as much as thresholds: the first version of the demo read a missing answer as 0.0, which meant "not an
incident" and a silent OBSERVE; it now escalates instead. "No unsafe automation" holds on a corpus where every
unsafe case is also labelled most severe, so a check on the *labelled* severity alone would produce it; on
Jev's own severity scores it would not. Jev rated the data-corruption incidents (labelled critical) at
{{dc_sev_min}}-{{dc_sev_max}} on a 0-3 scale; {{dc_stopped}}. Executors still need
idempotency, locks, approvals and tested rollback whatever model sits upstream.
*Source:* zeroops/policy.py; zeroops/schema.py; results/facts.json; build-vs-buy-gemini-openai.txt, "Primary
cost drivers" and "Externalize runbooks". *Label:* Our measurement, Independent.

### C8. The vendor is weeks old, hosted in one US region, and the model moves under an alias
Jev entered early access on 15 September 2026; public reports conflict on rate limits (80 requests per
second against 1,200 per minute), on whether sign-ups are open, and on SOC 2 status, and there is no
named production ITOps customer, no EU region, no on-premises option and no HIPAA BAA. The `jev-latest`
alias changes with each release; the demo now pins `{{jev_model}}` (native) and `{{or_model}}` (OpenRouter).
Incident records carry hostnames, usernames and sometimes customer data, so redaction and a signed DPA (zero
retention is enterprise-only, on request) come before any real ticket is sent.
*Source:* independent-review-claude.md, "Profile: Jev" and "Caveats" (largely secondary sources, to be
confirmed with TypeSafe); zeroops/adapters.py; decision logs `model` field. *Label:* Independent, Our measurement.

### C9. The API call is the easy part of the integration
In ServiceNow the documented pattern is a business rule or Flow Designer trigger calling an IntegrationHub
REST step (or a MID Server script for egress control), writing answer, confidence and model version to
hidden fields, with a fixed flow deciding what happens and falling back to existing rules on timeout or low
confidence. In PagerDuty the natural hooks are Event Orchestration rules, Custom Event Transformers and
webhooks ahead of notification or Automation Actions. The demo measured a median of {{p50}} ms and a 95th
percentile of {{p95}} ms calling the API directly from a workstation; latency inside IntegrationHub, behind a
MID Server, during an incident storm and under vendor rate limits is unknown.
*Source:* independent-review-claude.md, "Integration with an existing ServiceNow environment";
composable-stack, "Advanced Event Routing and Condition Languages"; build-vs-buy, "PagerDuty";
deliverables/7_results-report.md. *Label:* Independent, Our measurement.

### C10. Inference costs almost nothing; people and alternatives decide the economics
At list price ($0.042 per million input tokens, output free) our 12-question call costs about {{cost_1k}} per
1,000 incidents at roughly {{mean_tokens}} input tokens each (estimated: the native API reports no cost, so
OpenRouter's billed rate is applied), and a million 2,000-token routing decisions would cost about $84. The
real costs are question design, labelled data, threshold setting, red-teaming, re-validation at each model
release and a named owner, and the alternatives are real: tuned rules, features already licensed, a small
classifier on ticket history, an LLM with structured output, or a self-hosted Kev or Laya fine-tuned on your
tickets (untuned, they scored {{kev_cat}} and {{laya_cat}} on category in our run). The research's ">90% lower
LLM bill" has no measurement behind it; in our run {{escalated}} of {{n}} incidents were still sent to a person.
*Source:* independent-review-claude.md, "Build-vs-buy considerations"; deliverables/7_results-report.md;
composable-stack, "The Cascade Routing Pattern" and "Open-Source Substitution".
*Label:* Vendor claim (price), Our measurement, Judgement.

### C11. Regulatory duties depend on how each use is classified
Under the EU AI Act the substantial deployer duties (oversight by competent staff, keeping logs for at
least six months, monitoring, informing workers) apply to high-risk systems (Art. 26). Internal ticket
routing is probably not high-risk for most firms, but it could be where the system is a safety component
in operating critical digital infrastructure (Annex III point 2) or where it allocates work to, or
evaluates, individual staff (Annex III point 4); AI literacy (Art. 4) applies regardless. Typed inputs and
outputs make a good audit trail only if each call records the input or its hash, the model version, the
option order, the probabilities and the threshold version that acted.
*Source:* composable-stack, "Navigating the EU AI Act" (which overstates the general case);
independent-review-claude.md, "Integration ... Logging". *Label:* Judgement; needs legal review, and
the high-risk application dates have been subject to proposed delay, so check current status.

### C12. Someone has to own the questions, the thresholds and on-call trust
Model releases, new assignment groups and reorganisations all change the right thresholds, so they need
a named owner, a change process and a re-run of the backtest each time. On-call engineers will either
ignore a suggestion with a probability next to it or rubber-stamp it, and only an assist-mode trial with
override tracking shows which. The model does not learn from feedback; the label store built from
reassignments and closure codes is what improves, and it is reusable whichever tool is chosen.
*Source:* independent-review-claude.md, "Build-vs-buy considerations" (Maintenance; Effort and skills)
and component row 11; build-vs-buy, "Hybrid reference architecture" (feedback path).
*Label:* Independent, Judgement.

---

## 2. Questions IT needs to answer

Grouped by who owns the answer. "Settled by" is the evidence that would close the question. "Demo" is the
honest answer to "does the demo show this?"; for most questions it doesn't.

### SRE / operations

**Q1. What share of last quarter's P3/P4 incidents were reassigned at least once, and what median time did each reassignment add before the incident reached the group that resolved it?**
- Why: routing is the most plausible use; if reassignment is rare or cheap, there is little to gain.
- Settled by: ServiceNow `reassignment_count` and assignment-group audit history for one quarter, with time between group changes.
- Demo: No. It has no routing question and no ticket history.

**Q2. In a sample of 200 recent tickets, which first-line decisions were made from the text alone, and which needed a number, a time window or a live check of the system?**
- Why: the model reads text and does no arithmetic or date reasoning (C1).
- Settled by: two engineers tagging each decision in the sample; the share that is text-only.
- Demo: Partly. `zeroops/schema.py` shows what a typed question set looks like, and that severity and blast radius quietly depend on numbers in the text.

**Q3. What does a ticket actually contain when it is first routed: how long is it, how often is the short description empty or generic, and how often is it mostly pasted log output?**
- Why: thin text gives the model nothing; long noisy text degrades it (C3).
- Settled by: a length and field-completeness profile of 1,000 recent incidents at insert time.
- Demo: No. Its incidents are clean and hand-written, {{words_min}}-{{words_max}} words each.

**Q4. In the last year, how many P1/P2 root causes would not have appeared on any option list we could have written in advance?**
- Why: a choice question can only return options it was given, and novel failures are where a confident wrong answer is most likely.
- Settled by: postmortem review of 12 months of P1/P2s against a draft option list; the share that maps to "other".
- Demo: No. Its {{rc_jev_pct}} root-cause score reflects a list written to match its own {{n_templates}} templates.

**Q5. Which remediations (restart, scale-up, rollback, config patch) are already automated by rules or runbooks today, and what was their failure and manual-reversal rate last quarter?**
- Why: a gate adds value only where a reversible action already exists and is trusted (C7).
- Settled by: execution logs and outcomes from Rundeck, Flow Designer or Ansible.
- Demo: No. Its "automated" actions are never executed against anything.

**Q6. What does a missed major incident cost compared with a misrouted P3 or an unneeded rollback, in engineer-hours and customer impact?**
- Why: thresholds should follow from that cost ratio; in the demo, moving one threshold from {{page_cutoff}} to 0.80 changes automated incidents from {{autos}} to {{autos_080}} (C4).
- Settled by: postmortem data plus a per-error-type estimate agreed with service owners and finance.
- Demo: Partly. The Threshold Lab shows the trade-off mechanically, on synthetic incidents with no costs attached.

**Q7. Would on-call engineers act on a suggestion that comes with a probability, and how would we detect rubber-stamping?**
- Why: ignored suggestions add nothing; rubber-stamped ones remove the human check (C12).
- Settled by: an assist-mode trial logging accept and override rates, and the outcome of each override.
- Demo: No.

### ITSM / platform owner

**Q8. What does our ServiceNow licence already include for routing (Predictive Intelligence, Now Assist, the AIOps "AI specialists"), and what precision and coverage does it achieve on our assignment groups today?**
- Why: a new vendor has to beat what is already paid for (C2).
- Settled by: an entitlement check, then Predictive Intelligence solution statistics or a backtest of current assignment rules.
- Demo: No.

**Q9. How many assignment groups received incidents last quarter, and could a newcomer tell them apart from their names and descriptions?**
- Why: the model picks between options using their descriptions; accuracy drops with many similar options (Cribl, 28 classes) and a single question is capped at 255 options.
- Settled by: a count of active groups, a review of overlapping descriptions, and a decision on whether a two-step question is needed.
- Demo: No. It chooses among 7 failure categories and 8 services with hand-written descriptions.

**Q10. Is the final resolving group, closure code or root-cause field on past incidents accurate enough to score a model against?**
- Why: without trustworthy labels there is no way to set thresholds or measure accuracy.
- Settled by: an audit of 200 closed incidents comparing those fields with postmortems or resolver notes.
- Demo: No. Its labels were written by the person who wrote the incidents, and some are arguable.

**Q11. Where would the call sit (business rule, Flow Designer with IntegrationHub, MID Server), what p95 latency does that path allow during an incident storm, and what happens on timeout?**
- Why: the demo's latency excludes IntegrationHub, egress controls and rate limits (C9).
- Settled by: a sub-production prototype writing to hidden fields, load-tested at peak incident-insert rate.
- Demo: Partly. It shows the request and response, and that a timeout or error now escalates; latency was measured outside ServiceNow.

### Security

**Q12. Which incident fields can be written by someone outside IT (customers, third-party monitors, email-to-ticket, application logs), and does any of that text reach a question that gates an action?**
- Why: planted text moved Jev's answers in the Check Point and Octomind tests (C6).
- Settled by: a field-level data-flow map, then a red-team set of crafted tickets scored on probability shift.
- Demo: No. The corpus has no adversarial text, though the harness could run such a set.

**Q13. Does the answer change when the option order is shuffled, or when the same call is repeated?**
- Why: first-option bias is documented, and the demo's first-listed action was proposed {{first_ratio_words}} times as often as its labels called for (C5).
- Settled by: each test ticket run under three orderings, twice each; flip rate per question.
- Demo: Could, cheaply. Re-running the {{n}} incidents with shuffled options would test the mechanism, though not on your data.

**Q14. What leaves our network on each call (hostnames, usernames, customer identifiers), and can we redact it without removing the words the model needs?**
- Why: the service is hosted in US-West only, with zero retention on request (C8).
- Settled by: data classification of 1,000 incidents, and accuracy before and after redaction on the backtest set.
- Demo: No.

### Risk & compliance

**Q15. For each intended use, is it high-risk under the EU AI Act (a safety component of critical digital infrastructure, or allocating or evaluating staff), and so subject to Art. 26 deployer duties?**
- Why: the obligations follow the use, and the research's blanket "deployer duties" overstate the general case (C11).
- Settled by: a written legal classification per use case, recorded in the AI inventory.
- Demo: No.

**Q16. What must an audit record hold for us to explain an automated action six months later, and who signs off that it does?**
- Why: typed inputs and outputs are a good audit trail only if the log is complete.
- Settled by: internal audit reviewing a sample log against the control requirement.
- Demo: Partly. `results/decisions_*.jsonl` keeps the incident text, the model version, every probability, the thresholds used, the corpus version and the gate's reason, but not the option order or a tamper-evident hash.

### Procurement / vendor management

**Q17. Will TypeSafe put in writing a SOC 2 Type II report, a DPA with zero data retention, hosting regions, an SLA, rate limits, and the notice period before a pinned model version is retired?**
- Why: the product is weeks old and public reports conflict on rate limits, sign-ups and SOC 2 (C8).
- Settled by: the documents and the contract.
- Demo: No. It shows only that pinned versions (`{{jev_model}}`, `{{or_model}}`) can be requested today.

**Q18. If TypeSafe raises prices, retires the version we depend on, or stops trading, how fast can we fall back to rules or move the same questions to a self-hosted model, and what accuracy would we lose?**
- Why: startup risk; the exit path should be tested before any dependence, even in assist mode.
- Settled by: a tested fallback path and a backtest of the alternative on the same labelled set.
- Demo: Partly. The same wire schema ran Kev-4B and Laya unchanged, so the integration is portable; their untuned scores ({{kev_cat}} and {{laya_cat}} on category) say little about a tuned model.

### Finance

**Q19. What is the fully loaded first-year cost (engineering, labelling, evaluation, red-teaming, ownership), and how does it compare with tuning our rules or switching on features we already license?**
- Why: inference at about {{cost_1k_round}} per 1,000 decisions is immaterial; people cost dominates (C10).
- Settled by: a platform-team estimate for each option on the same scope.
- Demo: Only the inference line, estimated on short synthetic text.

**Q20. How many engineer-hours a month go on first-line triage and reassignment, and what is an hour of P1 outage worth to the business?**
- Why: there is no return on investment without a baseline cost.
- Settled by: ITSM time data or a two-week time study, plus business-impact figures from finance.
- Demo: No.

### Leadership

**Q21. Which single outcome do we want first (fewer reassignments, faster acknowledgement, fewer night pages, or automated fixes), and what result from a trial would make us stop?**
- Why: each outcome needs different questions, data, owners and risk controls, and a stop rule agreed in advance keeps a trial from drifting into dependence.
- Settled by: a one-page decision rule signed before any trial starts.
- Demo: No.

**Q22. How much autonomy are we willing to give a hosted model launched in September 2026: suggestions only, reversible actions on low-severity services, or more?**
- Why: this sets the security, compliance and engineering work required; the demo's "no unsafe automation" is 0 of {{unsafe_t}} unsafe scenario types (95% upper bound {{unsafe_upper}}), on a corpus where every unsafe case is also labelled most severe (C7).
- Settled by: a risk committee decision, recorded with its conditions.
- Demo: It shows what a code-side gate looks like (AUTO / ESCALATE / OBSERVE with a written reason). It says nothing about how safe that gate would be on our incidents.

**Q23. Who owns the questions and thresholds after go-live, who re-validates them at each model release, and who is accountable when the gate gets it wrong?**
- Why: thresholds drift with model releases, reorganisations and new services (C12).
- Settled by: a RACI and a change process for threshold changes, run through the normal change board.
- Demo: No. In the demo the thresholds sit in `zeroops/policy.py`, set by hand and never validated on held-out data.

---

## 3. The role of the Jev demo, and next steps

### What it is good for
- **Showing the mechanism concretely.** One call sends a short incident and 12 typed questions
  (`zeroops/schema.py`) and gets back choices, scores and probabilities. A short policy in code
  (`zeroops/policy.py`) turns them into AUTO, ESCALATE or OBSERVE with a written reason, and anyone can
  read the exact thresholds and see, for each incident, how close each check was.
- **Giving people something to react to.** An SRE can look at {{ex_id}} and argue with a gate that
  automated a rollback while the model put a {{ex_page_pct}} probability on paging a human. A security lead can
  see which text reaches the gate, and an auditor can read a real log line.
- **Making the questions concrete.** Most of the questions above were sharpened by something visible in
  the demo: "{{first_opt}}" proposed {{first_ratio_words}} times as often as labelled, a first version that read a
  missing answer as "not an incident", and automation falling from {{autos}} to {{autos_080}} incidents when one
  threshold moves by 0.10.
- **A reusable harness.** The adapter, the question format, the metrics (exact and acceptable action, missed
  incidents, unsafe automation by scenario type, calibration buckets) and the Threshold Lab can be pointed at
  real labelled tickets. The same wire schema already runs four backends (Jev native, Jev via OpenRouter,
  Kev-4B, Laya).

### What it cannot establish
- **Accuracy, calibration, safety or return on anyone's incidents.** The {{n}} incidents are
  {{n_templates}} templates with service names and numbers swapped, {{words_min}}-{{words_max}} words long,
  full of explicit cues, and labelled by their author.
- **Anything about real conditions:** alert noise, long payloads, CMDB and assignment-group quality,
  hundreds of options, novel failures, adversarial text, latency inside ServiceNow, or vendor stability.
- **The headline numbers carry caveats.** "No unsafe automation" means none of the {{unsafe_t}} unsafe scenario
  types was automated; with so few scenarios the true rate could be as high as {{unsafe_upper}}, and a crude rule
  on the labelled severity would also score zero here. Exact agreement with our action labels is
  {{exact_pct}}; the {{acceptable_pct}} "acceptable action" figure uses a list we wrote after the first run. Of the
  {{autos}} automated incidents, {{autos_wrong}} took an action other than the labelled one
  ({{autos_wrong_examples}}).

### Next steps: a staged way to find out
Each stage ends with a decision, so the work can stop as soon as the answer is clear. Durations are Judgement.

1. **Diagnostic (2-3 weeks; no data leaves your network).** Baseline reassignment, triage effort and out-of-hours
   volumes (Q1, Q20), what the current ServiceNow licence already does for routing (Q8), ticket and label quality
   (Q3, Q10), and the data and security constraints (Q12, Q14). *Decision:* is there a gap worth closing?
2. **Offline replay (3-4 weeks).** 2,000-5,000 closed tickets through the same harness, peak periods and incident
   surges included, scored against the final resolving group and compared with current rules and simple
   alternatives (option D below). Needs a DPA and redaction first (Q14, Q17), or a first pass on a self-hosted
   model. *Decision:* does it beat what runs today, by enough to matter?
3. **Shadow, then assist mode (6-8 weeks).** Answers written to hidden fields inside ServiceNow with routing
   unchanged, then suggestions with override tracking (options E and F). *Decision:* how much autonomy, under
   which owner (Q22, Q23)?

Where an outside team can help: bringing the harness, question design and gate from this demo; baselining the
estate's own ServiceNow data and framing the stop/go rule for each stage; working alongside the platform and data
teams on the replay; benchmarking what is already licensed against what sector peers are doing (platform AIOps
features, an in-house classifier, an LLM with structured output); and supporting the compliance and ownership
calls (NIS2, DORA or EU AI Act classification, who owns the questions and thresholds). The harness runs any model,
so the choice of tool stays open.

### Ways the demo could be extended
The building blocks behind the stages, with rough effort. Effort figures are Judgement.

| Option | Questions it informs | Rough effort | Notes |
|---|---|---|---|
| A. Finish the harness basics: a held-out split for choosing thresholds, logging option order and an input hash (fail-closed handling, pinned model versions and threshold logging were added on 2026-10-04) | Makes later results credible; Q16 in part | 1-2 days | No new data needed |
| B. Shuffle-and-repeat run on the existing incidents | Q13 (mechanism only) | 1-2 days | Inference cost: cents |
| C. 30-50 adversarial variants (instructions planted in log lines and descriptions), scored on probability shift of gating questions | Q12 (mechanism only) | 3-5 days | Synthetic, so indicative only |
| D. Offline replay of 2,000-5,000 closed tickets: a routing question built from active assignment groups, scored against the final resolving group, compared with current rules or Predictive Intelligence, a simple classifier on ticket history and a structured-output LLM | Q3, Q8, Q9, Q10, Q13 on real data; Q19 in part | 2-4 weeks, mostly data extraction and redaction | Needs DPA and redaction first (Q14, Q17), or a first pass on a self-hosted model so no data leaves; Jev inference about {{cost_5k}} for 5,000 tickets |
| E. Live shadow mode: IntegrationHub or MID Server call writing hidden fields, routing unchanged | Q11, drift, real coverage | 2-4 weeks build plus 4+ weeks observing | Needs security review; Q15 classification beforehand |
| F. Assist mode with override tracking, after E | Q7, Q21 | 4-8 weeks | Needs an owner for thresholds (Q23) |

The research files these considerations draw on are model-generated; their provenance and weak sources are
listed in `research/README.md`.
