# The IT Incident Decision Market — landscape & positioning

**Positioning thesis (supplement, not replacement).** Jev is best adopted as a
**decision-and-confidence overlay** that plugs into the IT-operations estate you already run —
ServiceNow ITOM, PagerDuty, Datadog, Dynatrace, or an open stack — **not** as a rip-and-replace
of those platforms. It does not compete with chat LLMs, and it does not try to be the system of
record, the telemetry lake, the on-call tool, or the runbook runner. It replaces one narrow thing:
the **brittle decision logic** inside those tools (assignment rules, correlation heuristics, runbook
triggers) with a *typed, calibrated* judgment — schema'd answers (Choice/Score/Noul) with
probabilities and confidence in one parallel, low-latency, low-cost call.

> **Why supplement beats replacement:** the incumbents' value is the system of record (CMDB/ITSM),
> the 200+ integrations, the workflow/on-call ownership, and the audit/compliance posture. Ripping
> that out is a multi-year, high-risk migration. Overlaying a small decision service on top captures
> most of the benefit with none of the migration risk — and every incumbent is *already* adding this
> layer (Dynatrace guardrails, Datadog Bits Guardrails, Splunk Event iQ confidence, incident.io
> Nexus), which validates the category without requiring you to buy their whole suite.

> Draft synthesized from vendor docs/pages and analyst/tech-press research (Oct 2026). Numbers are
> vendor-reported unless marked independent. See `Sources`.

---

## 1. Market map (six categories)

| Category | Representative vendors | Decision mechanism | Calibrated confidence? | Autonomy gating | Pricing |
|---|---|---|---|---|---|
| AIOps / event correlation | ServiceNow Event Mgmt, BigPanda, Moogsoft→Dell, Splunk ITSI, IBM Cloud Pak | Rules + ML clustering + topology | Rare (Splunk Event iQ "confidence-based"; PagerDuty % likelihood) | Alert rules + workflows; human-in-loop | Per user/node/ingest; quote-based |
| Observability-native AI | Dynatrace Davis, Datadog Watchdog/Bits, New Relic | Deterministic causal graph + LLM agent | Ranking, not a calibrated scalar | Policy guardrails; approval; read-only default | Consumption (data units, AI credits, hosts) |
| Agentic AI SRE (startups) | Resolve.ai, Traversal, Cleric, NeuBird, Metoro | LLM agents + world model/context graph | Mixed; some name confidence, few calibrate | Read-only default; "earned write"; human approval | Subscription; some per-node |
| Incident management + AI | incident.io, Rootly, FireHydrant(Blameless), PagerDuty | Workflow + agentic RCA | incident.io cites confidence + daily backtesting | PR-only / approval; no un-gated writes | Per seat + AI add-ons |
| Runbook / automation | Rundeck (PagerDuty), StackStorm, Ansible AAP + EDA | Deterministic rules/workflows | No (deterministic by design) | Rulebook design; approvals | OSS + enterprise |
| Cloud-provider agents | AWS DevOps Agent, Azure SRE Agent, Google | LLM agent over control plane | Not exposed as calibrated | "Within policy guardrails and human approval" | Usage (Azure Agent Units, etc.) |

**The real head-to-head** for "automated incident decisions" is not LLM vs LLM — it is
**context/world-model + calibrated confidence + safe action**, wrapped by whoever owns telemetry or
the on-call workflow.

---

## 2. ServiceNow (the incumbent to beat)

- **Stack:** ITOM = Discovery + Service Mapping + CMDB/CSDM → **Event Management** → AIOps → Now
  Assist → Automation Engine (Flow Designer + IntegrationHub + RPA Hub). **Rundeck is NOT
  ServiceNow — it is PagerDuty's.**
- **Noise reduction / correlation:** dedup by "message key", then correlation/grouping in a fixed
  **R→A→M→C** order (Rule → Automated ML → Manual → CMDB). One group per alert; closing a primary
  cascades to secondaries.
- **Scoring:** alert priority = business-service criticality (weight **10,000,000**) + severity +
  CI-type importance; recalculated ~every 30 min into Urgent/High/Moderate/Low. Incident priority =
  Impact × Urgency.
- **Decision to act:** an **alert rule** decides create-incident vs invoke-remediation-flow vs leave.
  Auto-remediation runs through Flow Designer/IntegrationHub; wording is "automatically triggered
  **or initiated**" — much remediation is operator-triggered. "Closed loop" completes only when the
  source sends a **clear** event.
- **GenAI/agents:** Now Assist for ITOM (alert summaries, similar incidents, next steps); 2026
  "AIOps AI Specialist" recommends/acts then **reassigns to the human owner** — explicitly
  human-in-the-loop.
- **Gaps (documented):** CMDB/CSDM quality is the load-bearing dependency; no exposed *calibrated*
  confidence gate for auto-remediation; grouping-window opacity and duplicate-incident risk; pricing
  opacity / ELAs / SKU repackaging (Gartner via The Register); steep customization cost.
- **Pricing:** custom-quoted. Third-party estimates: ITSM ≈ $90–150/user/mo; **ITOM ≈ $150–200+
  /user/mo**; 500 ITSM fulfillers can exceed $1M/yr in licences alone; services ≈75% of Year-1 spend.

## 3. Observability incumbents (deterministic detection + LLM assistants)

- **Dynatrace:** Davis **causal AI** over **Smartscape** topology + Grail lakehouse; problems
  correlate context-aware events; fault-tree RCA ranks contributors; agentic workflows run approved
  actions under **policy guardrails**. Markets "deterministic AI, unlike LLMs."
- **Datadog:** Watchdog (statistical baselines) + **Bits AI** (investigation, code fixes, one-click
  K8s actions) with **Bits Guardrails** = **Ask** (approval) or **Deny** (recommend-only). AI
  Credits are a separate meter.
- **New Relic:** anomaly/predictive alerts (Holt-Winters); correlation "Decisions" with **topology
  correlation within 5 hops**; AI assistant + Workflow Automation; no explicit RCA confidence.
- **Splunk ITSI:** correlation searches → notable events → **episodes** via aggregation policies;
  **Event iQ** adds AI summaries and **confidence-based root-cause guidance**; actions are
  ticket/SOAR-driven.
- **IBM (Instana / Cloud Pak→Concert Operate):** topology-based grouping over a unified graph;
  Instana **Intelligent Incident Investigation** (agentic, GA Dec-2025) walks the dependency graph and
  **generates Bash/Ansible remediation scripts for review** — review-gated autonomy.
- **PagerDuty:** AIOps = event correlation (ML alert grouping, "Probable Origin" gives up to **3
  origins with % likelihood**); **Runbook Automation** (Rundeck) executes; SRE Agent executes "with
  human approval."
- **BigPanda:** docs pipeline = dedup → filter → alert formation → incident correlation (max 300
  alerts/incident) → classification; **IT Knowledge Graph** enriches; **Biggy** LLM assistant;
  agentic workflows with **guardrails** + audit.
- **Moogsoft → Dell AIOps:** ML "Situations" from text/time/topology correlation; Dell **bundles
  AIOps free with ProSupport** — a pricing pressure signal for the whole category.

## 4. Agentic AI SRE (the category Jev most directly attacks)

| Vendor | Mechanism | Auto-remediation | Safety/confidence |
|---|---|---|---|
| Resolve.ai | LLM agents + Hivemind context; "one correct answer at best price" | Yes (primary on-call) | Enterprise controls; escalates |
| Traversal | LLM + **Production World Model** (causal graph) + Causal Search Engine | Yes (read-only default) | 82% RCA claimed; read-only by default |
| Cleric | LLM agents + service map; compounding memory | **No auto-merge; opens PRs** | Read-only default; audited |
| NeuBird | LLM + Agent Context Engine; governed multi-model gateway | Suggest/Recommend/**Act** tiers | **Human approval on every write** |
| Metoro | eBPF telemetry + K8s context → LLM agents | Opens fix PRs | SOC2; BYOC/on-prem |
| incident.io | **Nexus** + adversarial self-check | **PR only** | Names confidence + **daily backtesting** |
| Rootly / FireHydrant | Agentic RCA + incident workflow | Suggested fixes | Guardrails; human command |

**What they all concede:** autonomous production writes are the risk. Nearly every vendor gates them
behind human approval, read-only defaults, or "earned write access" — because *unconstrained* LLM
confidence is not trusted.

## 5. What buyers actually pay for

1. **MTTR reduction** (universal headline) and **on-call toil/noise** reduction.
2. **RCA accuracy**, not just speed (Traversal, NeuBird cite 82–94%).
3. **Safe automation + governance**: approval gates, policy tiers, RBAC/SSO, SOC 2, audit trails,
   zero-retention, BYOC/BYOM.
4. **Institutional memory** (Torq Recall/Reflex, NeuBird Context Engine, incident.io Nexus).
5. **Cost predictability** — a reaction against token-metering (per-node pricing, model budgets).
6. **No rip-and-replace**: read-only defaults, 50–750+ integrations, MCP/A2A.

## 6. Limitations of the LLM-agent approach (the opening for Jev)

- **Confident-but-wrong RCA.** Traversal's own benchmark shows frontier models with tool access
  returning "plausible, confident, wrong" causes on simple incidents.
- **Uncalibrated confidence.** The vendors who take this seriously build *separate per-tenant
  classifiers* (Torq **Reflex**) or backtest daily (incident.io) — evidence raw LLM confidence isn't
  trustworthy. Most expose no calibrated scalar at all.
- **Non-determinism** (audit/reproducibility hostile), **latency** (model+MCP investigations took
  19.7–36 min vs 9.5 min in one benchmark), **cost/token sprawl**, **context-gap failures**,
  **amnesia** without a memory layer.

## 7. Where Jev competes vs complements

**Competes:** the decision/RCA/confidence core (Traversal's world model, Torq's Reflex, incident.io
Nexus), ad-hoc rule engines (Ansible EDA, StackStorm, Rundeck), and per-vendor approval policy.

**Complements:** as a **vendor-neutral contract + calibration + guardrail substrate** —
- define the schemas for Alert/Incident/Hypothesis/Action and validate LLM output against them;
- attach a **calibrated** confidence and route by threshold (auto vs human);
- sit *above* executors (Rundeck/EDA/Tines/Torq) to turn brittle YAML into typed, evaluated policy;
- act as the **LLM cost/latency governor** — handle the high-confidence majority deterministically and
  call the expensive agent only when the decision is genuinely uncertain;
- be the **audit/replay layer** (typed decision + inputs + model binding).

**One-line pitch:** *"Make any AI SRE agent's decisions typed, calibrated, deterministic, and
auditable — and only call the expensive model when it's truly uncertain."*

## 8. Benchmark reality check

- **ITBench (IBM, ICML'25)** and **AIOpsLab (Microsoft, MLSys'25)** are the credible public
  task taxonomies (Detect→Localize→Analyze→Mitigate; SRE/CISO/FinOps). Frontier models scored
  **below ~50%** on ITBench-AA SRE tasks — the task is not solved.
- **Vendor benchmarks** (Traversal Elo, NeuBird 94%, Datadog 70% MTTR) are self-reported and
  unaudited; treat as directional. RCAEval/TrainTicket-style datasets are useful for *localization*
  but not end-to-end decisions. Our own corpus (56 labeled incidents, 14 archetypes) is small but
  reproducible and doubles as a regression gate.

## 9. Implications for this project

1. **Do not pitch "better than ChatGPT."** Pitch a *decision layer* with calibrated confidence —
   the thing every serious vendor is now trying to bolt on (Reflex, Nexus, Event iQ).
2. **Anchor on the gate, not the model.** "Act only when confidence is high and the action is
   reversible; escalate with the probability trace" is the language buyers already use.
3. **Complement, don't rip out.** Jev sits between the telemetry/correlation layer (ServiceNow,
   Dynatrace, Datadog) and the executor (Rundeck/EDA/Tines), which is the unowned seam.
4. **Attack cost/latency/non-determinism** of agentic RCA: handle the confident majority in ~0.1s for
   a fraction of a cent; escalate only the uncertain minority to an LLM agent.
5. **Prove safety, not accuracy alone.** The buyable metric is *unsafe-action rate at an automation
   target* — exactly what our demo measures (0% unsafe at ~36% automation).

---

## 10. Supplement map — where Jev plugs into an existing estate

The enterprise platforms are multi-tier pipelines (ingest → dedup → triage → correlate →
remediate). Jev overlays **one layer** — the semantic decision + confidence gate — and calls the
incumbent for everything else:

| Pipeline stage | Incumbent (kept) | Jev's overlay | Measured evidence |
|---|---|---|---|
| Triage / routing | ServiceNow alert rules; PagerDuty routing | `Choice`/`Score` on the alert payload → category, owner, severity | 80% category, 100% root-cause match (56 incidents) |
| Evidence grouping | BigPanda, Splunk ITSI correlation | Pairwise `Noul` "do A and B share a cause?" over active threads | design (not yet benchmarked) |
| Remediation gating | ServiceNow flows; PagerDuty runbooks | `Noul` policy gate **before** the existing runbook fires | 0% unsafe autos at ~36% automation |
| Deep RCA narrative | LLM agents (Resolve/Traversal/…) | Escalate **only** the uncertain minority to the LLM agent | ~64% of cases need no LLM at all |

**What stays put:** CMDB/ITSM as system of record, the ingestion/telemetry lake, on-call and
paging, runbook execution, and audit/compliance reporting. Jev is invoked as a service and returns
a typed decision plus confidence; the incumbent records and acts on it.

## 11. Two deployment patterns (both supplements)

**Pattern A — overlay (recommended).** Keep ServiceNow / PagerDuty / Datadog exactly as they are.
Insert Jev as a service the platform calls at its decision points: before assignment/routing, and
before a runbook executes. The platform stays the system of record; only its decision logic changes.

**Pattern B — greenfield open stack.** When there is no incumbent, or for a new domain, assemble
the pipeline below. The **Decide** box is Jev; every other box is replaceable.

```
 Ingestion        Decision (semantic)         Workflow            Execution
 Vector/Fluent ─▶ Jev (Choice/Score/Noul) ─▶ Temporal /     ─▶ Kubernetes API · Ansible ·
 Bit ─▶ Redpanda   typed + calibrated          Windmill /         Rundeck · cloud APIs
 (Kafka)           confidence, ~0.1s,          Prefect
                   ~$0.06 / 1k
                        │
                        └─▶ (only when uncertain) heavy GenAI: Claude / GPT-4o for narrative RCA
```

- **Ingestion:** Vector or Fluent Bit → Redpanda/Kafka for high-throughput telemetry.
- **Decision:** Jev returns typed routing, severity, and a policy gate — deterministic to branch on.
- **Workflow:** Temporal/Windmill/Prefect own timeouts, escalation, and runbook execution.
- **Heavy analysis (optional):** the expensive LLM is invoked *only* on Jev's low-confidence cases.
- **UI:** Slack app + a thin Next.js/Retool incident room.

Either pattern is a **supplement**: the decision layer is explicit, typed, and swappable; the
surrounding platform — telemetry, workflow, execution, on-call — is untouched. This mirrors what the
incumbents build internally (deterministic core + LLM at the edges + approval gating), except the
decision layer is yours and portable, not locked inside one vendor.

## 12. Corrections to common (including LLM-generated) claims

- **Cost/latency:** our measured Jev figures are **~0.1 s p50** and **$0.057 per 1,000
  incidents** (~$0.000057 each, from `usage.cost`). Do not state a per-million-token price as if it
  were the per-incident cost; they are different units.
- **Latency:** the earlier "~0.5 s" figure is high for our setup — single calls measured 0.17–0.35 s,
  corpus p50 ~0.1 s.
- **"Sherlocks AI":** verify the exact product name before citing; treat as unverified.
- **ServiceNow routing:** rule-driven with ML assistance — not "purely slow ML."
- **Correlation:** pairwise `Noul` grouping is a *supplement* to topology correlation, not a
  wholesale replacement for a CMDB/topology graph.

---

## 13. Reality check — independent evidence on Jev (Oct 2026)

Sources: the Claude deep-research report, now `research/independent-review-claude.md` (it was cited here as `demo/market-research-claude.md`, which no longer exists).

- **Name/position.** "JEV" = TypeSafe's Jev. It is a **primitive, not a platform** — no ingestion,
  correlation, CMDB, workflow, on-call, or remediation. Every use case is your glue code.
- **Mixed evidence.**
  - **SREGym:** Jev-assisted SRE agent passed **24/50** vs **20/50** without Jev (40%→48%) on 10
    Kubernetess problems ×5; two problem types regressed; measured pass-rate, not time-to-diagnosis.
  - **Cribl (28-way log classification):** Jev misclassified **2–3× more** than a purpose-built
    classifier, but was **~18× faster and ~20× cheaper**.
  - **Cribl (agent grading):** >92% agreement with an LLM-judge committee at **~1% of the cost**.
  - **Jev Logs:** routed 99.3% of HDFS anomalies but 99.16% of all records — it filtered almost
    nothing. Never use it as an archive/filter gate.
- **Security is the headline risk.**
  - TypeSafe's own "jaggedness" page: adversarial content **can move the answer**; **option-order
    bias**; no reliable arithmetic/counting; dates read as text; context rot; literal reading.
  - **Check Point (Sep-24):** the strongest attacker broke Jev **25/27** runs, ~4th turn, ~$0.50 per
    break; an anti-injection instruction cut breaks only 18→17/27.
  - **Octomind:** one planted field cut a "block `rm -rf ~/.ssh`" probability from **0.76 → 0.48**.
  - Mitigation is architectural: typed field separation, **no action authority**, human approval,
    option-order shuffling, and never feeding tool output/attacker-controllable text into
    action-gating questions.
- **Maturity.** `jev-1.13`, ~3 weeks old; `jev-latest` drift (pin versions); hosted US-West, no
  documented EU region; SOC 2 likely (verify the report); DPA + ZDR available; **no named ITOps
  production customer** yet.
- **Pricing.** List **$0.042 / million input tokens**, output free (our measured OpenRouter cost of
  $0.057 per 1,000 incidents is consistent with ~2k tokens/incident).

## 14. Component build / buy / supplement

| Component | Verdict | Where Jev fits |
|---|---|---|
| Ingestion / observability | Build (OTel + Prometheus/Grafana) or buy | none (or minor "deserves analysis" scoring) |
| Anomaly detection | Buy / keep — keep it numeric | **no fit** (weak at numbers) |
| Event correlation & dedup | Hybrid: OSS fingerprinting + commercial ML | supplement: `Noul` "same incident?" after dedup |
| Enrichment / CMDB / topology (system of record) | Buy / keep ServiceNow | supplement: map free text → CI/team (`Choice`) |
| Root cause analysis | Buy topology RCA or pilot an AI SRE agent | supplement: rank candidate tests / gate early diagnosis |
| **Triage / prioritization / routing** | **Strongest build candidate** | **primary pilot target** (`Choice`/`Score`/`Noul`) |
| ITSM workflow integration | Keep ServiceNow as system of record | called from Flow Designer/IntegrationHub |
| On-call & communication | Buy (safety-critical) | minor (paging-urgency scoring, shadow only) |
| Remediation / runbooks | Build is viable (Rundeck/AWX/StackStorm) | **gate only, never authority** |
| GenAI assistants (summaries, postmortems) | Buy summaries; pilot agents | cheap router/judge inside an agent |
| Learning / feedback loops | Build the label+eval layer yourself | fits as an evaluator |

## 15. Pilot framework (6–8 weeks, shadow mode)

- **Use cases:** A) assignment-group routing (`Choice` + "information sufficient?" `Noul`);
  B) triage scoring (`Score` impact/urgency + "possible major incident"/"likely duplicate" `Noul`);
  C) optional agent guardrail — evidence-sufficiency gate before a remediation agent proposes.
- **Phases:** weeks 1–2 offline backtest on 2,000–5,000 labeled incidents; weeks 3–6 live shadow
  (write to hidden fields, change nothing); weeks 7–8 assist (suggest above threshold, still no
  auto-route). **Out of scope:** anomaly detection, remediation execution, paging, regulated data.
- **Pass bars:** routing accuracy ≥ current rules/Predictive Intelligence and ≥90% at threshold;
  ≥50% auto-routable at target accuracy; calibration monotonic with high buckets ≥95%; false-merge
  <2%; major-incident recall ≥95%; option-order flips <5%; no successful injection on
  routing-critical fields; p95 <1 s; accuracy drift <2 pts across Jev releases.
- **Integration:** ServiceNow business rule / Flow Designer → IntegrationHub REST step (or MID
  Server) → write `u_jev_group`, `u_jev_confidence`, `u_jev_model_version`; a deterministic flow
  decides (nothing in shadow, suggestion in assist); **fall through to existing rules on timeout or
  low confidence**; log state hash, option order, model version, probabilities, confidence.
- **Do not:** give Jev action authority, or use it to justify displacing ServiceNow ITOM. Compare
  against what you already own (Now Assist, Predictive Intelligence, your SRE agent).

---

## Sources (selected)
- ServiceNow: Event Management data sheet; Alert correlation & grouping (Community); Alert priority
  (Community/KB KB0870754); Now Assist for ITOM docs; Predictive AIOps (Wayback); Gartner pricing via
  The Register (2022); AppOmni KB exposure (BleepingComputer, 2024).
- Dynatrace: docs — Davis AI, Anomaly detection, Root cause analysis concepts, Agentic & generative AI.
- Datadog: docs — Watchdog, Watchdog RCA, Events correlation, Bits AI (Investigation/Remediation/
  Detection), AI Credits.
- New Relic: docs — Predictive alerts, correlation Decisions; pricing. Splunk: ITSI Event Analytics,
  Smart Mode, Event iQ, pricing. IBM: Instana Intelligent Incident Investigation (GA Dec-2025),
  Cloud Pak for AIOps / Concert Operate. PagerDuty: AIOps, Intelligent Alert Grouping, Probable
  Origin, Runbook Automation, AIOps pricing. BigPanda: Events-to-Incidents lifecycle, IT Knowledge
  Graph, Biggy. Moogsoft/Dell AIOps.
- Startups: Resolve.ai (Series A $125M, Feb-2026), Traversal (benchmark blog; $48M Series A),
  Cleric, NeuBird, Metoro, incident.io, Rootly, FireHydrant/Blameless (2024), Shoreline→NVIDIA (2024).
- Runbook/automation: Rundeck/PagerDuty, StackStorm, Red Hat Event-Driven Ansible, Torq (Context
  Graph/Reflex/Recall), Tines, Blink, Cortex.
- Benchmarks: ITBench (ICML'25), AIOpsLab (MLSys'25).

*Full URL list is maintained in the deep-research prompt output; regenerate/extend with Claude deep
search for the final version.*
