# Industry evidence collected via the Kimi online app (October 2026)

The figures on the deck's industry slides (3 and 4) come from a research pass done with the Kimi
online app on 2026-10-04, not from the files in this folder. They are reproduced here so the deck
stays traceable. **None of the underlying sources has been re-checked line by line in this repo**;
treat them as third-party reporting and confirm before quoting them in writing. The deck labels them
as shown below.

| Claim as used on the deck | Label | Note |
|---|---|---|
| Microsoft made Azure SRE Agent generally available in March 2026 and reports 1,300+ agents on its own services, 35,000+ incidents mitigated, 20,000+ engineering hours saved | Vendor-reported (Microsoft), via press coverage | Scale figures are Microsoft's own |
| PagerDuty's study of 500 IT leaders: average customer-facing incident 175 minutes to resolve, nearly $794,000 in cost, incident counts up 43% year on year (2024) | Vendor-commissioned study | Survey-based |
| Splunk / Oxford Economics: unplanned downtime about $200M a year for a large enterprise | Third-party estimate | Modelled, not measured per firm |
| Gartner: 70% of enterprises running agentic AI on IT infrastructure by 2029, up from under 5% in 2025; April 2026 survey of 782 I&O leaders: 28% of I&O AI use cases fully succeed | Independent (as reported in secondary coverage) | Gartner text not directly accessed |
| 2026 SRE Report: toil at 34% of engineer time | Independent (survey) | |
| Resolve AI raised $125M at a $1B valuation (Feb 2026) | Independent (press) | Also in `independent-review-claude.md` |
| DigitalOcean uses Traversal's causal-search RCA; 36,000 engineering hours a year reported saved | Vendor-reported (case coverage) | |
| incident.io's AI SRE triages alerts and drafts postmortems for Netflix, Etsy and 600+ companies | Vendor-reported (customer reporting) | |
| BigPanda correlates alert floods for Fortune 500 IT operations (Intel, Cisco, United, Marriott) | Vendor press materials | |
| PagerDuty SRE Agent GA Oct 2025; Datadog Bits AI SRE GA Dec 2025; Dynatrace Autonomous SRE Agent announced Jul 2026; Azure SRE Agent and AWS DevOps Agent GA Mar 2026 | Independent (third-party reporting) | Availability dates only |

## Why they are on the deck

They answer "why now": AI SRE became a real category in 2026, the cost pressure is documented, and
adoption lags ambition. None of them is needed for the demo's own results, which are all
*Our measurement* from `../../work/results/`.

## How to use them

Quote with the label and the year, and check the original source before putting any of these figures
in writing to a client. The weakest are the modelled downtime estimate and the Gartner figures read
through secondary coverage.
