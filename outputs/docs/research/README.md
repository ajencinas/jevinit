# Research

Background reading collected for the demo: the incident-tooling market, where a typed decision model could fit, and what has been published about Jev. Almost all of it was generated with AI tools (Claude, Gemini, OpenAI deep research) from public sources. The sources are cited but nobody has checked them line by line, and several of them are blogs or vendor marketing. Use these files to find sources, and check a source before quoting a figure from it.

The demo and its results are in `../../outputs/` and `../../work/results/`. Numbers measured in the demo live only in `../../outputs/7_results-report.md`; where a file here quotes a demo figure, the report wins.

## Files

| File | Where it came from | What it covers |
|---|---|---|
| `industry-evidence-kimi-online.md` | Research pass with the Kimi online app (2026-10-04); sources not re-checked line by line here | The deck's "why now" figures: AI SRE category (Microsoft agent counts), incident-cost studies (PagerDuty, Splunk/Oxford), Gartner adoption figures, vendor case studies |
| `landscape-synthesis.md` | Written for this repo with AI assistance, from the files below plus vendor pages. A draft, written before the narrative stopped recommending a pilot, so its opening "positioning thesis" argues a case. | Market map; where Jev competes with or complements existing tools; a component-by-component build/buy table; independent evidence on Jev (§13) |
| `independent-review-claude.md` | Claude deep-research export, model-generated. "Independent" means independent of TypeSafe. It is a model-written literature review. The shadow-mode pilot it recommends is the model's suggestion; this repo makes no recommendation. | Jev's maturity; documented failure modes (prompt injection, option order, no arithmetic, long inputs); security tests (Check Point, Octomind); ServiceNow integration; a trial outline |
| `independent-review-claude-source.md` | **Byte-identical copy of `independent-review-claude.md`** (checked with `cmp`, same MD5). It is not a separate raw export. Read either; one of them can be deleted. | Same as above |
| `build-vs-buy-gemini-openai.docx` / `.txt` | Gemini/OpenAI deep research, model-generated. The `.docx` is the original export; the `.txt` is extracted text and drops the recommendation table and several lists. | What is easy or hard to build yourself; the four architectural classes; an event contract; layered correlation; a phased build/buy roadmap. It never mentions Jev. |
| `composable-stack-and-compliance-gemini-openai.docx` / `.txt` | Gemini/OpenAI deep research, model-generated. The `.txt` loses at least one number ("a probability of ."). | Event routing (PagerDuty, webhooks); OpenTelemetry layouts; typed models compared with LLMs and with Laya and Kev; injection risk; EU AI Act, SOC 2, HIPAA |

Label every number you reuse: *Our measurement* (from `../../work/results/`), *Vendor claim*, *Independent*, or *Third-party estimate* when the source is a blog or consultancy. Give the date; product facts here change quickly.

## Weak or wrong claims we found

From the claim-by-claim audit done for the narrative rewrite (October 2026). Don't quote these without checking the original source.

In `composable-stack-and-compliance-gemini-openai`:
- It says a 0.90 confidence from Jev can be trusted as 90% accuracy. Pydantic, quoted in the independent review, calls the confidence "a margin, not a probability that the answer is right", and the demo's calibration table doesn't show it either (`../../outputs/7_results-report.md`, section 4).
- ">90% lower LLM bill" for a rules-then-Jev-then-LLM cascade comes from a personal blog. Nothing in this repo builds or measures a cascade.
- Its per-user ITSM/ITOM prices and "$20,000 to $25,000" baseline integration cost come from consultancy and dev-shop blogs. ServiceNow quotes privately, ITOM is generally not priced per user, and the integration figure is implausibly low for an enterprise ITOM programme.
- Its latency and context figures for Jev, Laya and Kev come from blogs and disagree with what the demo measured.
- Its table ranks high-cardinality routing as Jev's best fit, which Cribl's 28-class result (in the independent review) contradicts.
- It applies EU AI Act deployer duties (human oversight, logging) to incident triage in general. Those duties attach to high-risk uses, which ticket routing usually isn't; the fine levels it quotes are correct, but the top tier is for prohibited practices. Its sources are compliance-vendor blogs. Get a legal reading.
- Parts read as generated filler ("absolute immunity to syntax parsing errors", "financially catastrophic") and cite SEO blogs.

In `landscape-synthesis.md`:
- "200+ integrations" and "$1M/yr for 500 fulfillers" have no source.
- The Cribl figure "~18× faster, ~20× cheaper" compares Jev with an LLM (GPT-5.6 Terra). The purpose-built classifier that beat Jev on accuracy is a different comparator.
- "~2k tokens per incident" doesn't match the demo's logs; use the token counts in `../../outputs/7_results-report.md`.
- §10 presents the demo's failure-category accuracy as routing evidence. The demo has no routing question.
- The "positioning thesis" describes Jev's probabilities as calibrated. The demo's data doesn't show that.

In `independent-review-claude.md`:
- Several vendor facts (SOC 2 status, rate limits, whether sign-ups are open) rest on secondary sources that conflict. Confirm them with TypeSafe in writing.
- "Three weeks old" and "US West only" were true in early October 2026 and will date.

## What the research says, briefly

- Incident tooling splits into systems of record (ServiceNow, BMC), observability (Dynatrace, Datadog, Splunk, New Relic, Elastic, Instana), event correlation (BigPanda, Moogsoft, now Dell) and on-call (PagerDuty, Opsgenie). Jev is none of these. It is a single API call made from your own code or from one of those tools.
- Replacing a CMDB, topology or on-call tool is expensive and slow. Adding a decision step on top of the existing tools is the cheaper thing to try, and the incumbents are adding similar confidence signals of their own.
- The reports propose rules first, a typed model next, and a large LLM only when the typed model is unsure, with a confidence check before any action. This repo neither builds nor measures that.
- Confidence scores are useful as a gate only if they track accuracy on your own data. Independent tests found prompt injection, option-order bias, no arithmetic and falling accuracy on long inputs, so the published advice is to keep action authority outside the model.
- EU AI Act duties depend on whether a given use counts as high-risk. Ticket routing usually doesn't, but that needs a legal check.

## Independent evidence on Jev so far

All *Independent*, small samples, from the Claude review's sources:
- SREGym: a Jev-assisted SRE agent passed 24 of 50 Kubernetes tasks against 20 of 50 without it; two problem types got worse, and the study measured pass rate only; time to diagnosis wasn't measured.
- Cribl: Jev misclassified 2-3 times more often than a purpose-built classifier on a 28-class log task, while being much faster and cheaper than the LLM it was compared with.
- A community benchmark of Jev Logs routed 99.3% of anomalies to analysis, but also 99.16% of all records, so it filtered almost nothing.
- Check Point's strongest attacker broke Jev in 25 of 27 runs; Octomind moved a "block this command" probability from 0.76 to 0.48 with one planted field.

Vendor noise-reduction and MTTR figures (ServiceNow, PagerDuty, LogicMonitor, BigPanda) are marketing claims. Product status changes quickly: Opsgenie support ends April 2027, Moogsoft is now Dell, Blameless is now FireHydrant, Shoreline is now NVIDIA, and Rundeck is part of PagerDuty. Re-check before citing.
