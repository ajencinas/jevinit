"""Synthetic-but-realistic labeled incident corpus for the ZeroOps autopilot.

Each incident is one alert + enrichment (metrics, changes, logs, dependencies) and a
ground-truth record: the true failure category, root cause, severity, correct first
action, and whether automating that action is safe. Deterministic (seeded).
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, asdict, field
from typing import Any


@dataclass
class Incident:
    id: str
    archetype: str
    state: str
    ground_truth: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Each archetype: labels (category, root_cause, action, sev, auto_safe, real_incident),
# an optional fixed `dep`, and text templates. Template fields: {svc}, {dep}, {handler},
# {fw}, {fw2}, {cfg}. `origin` says which component the fault originates in ("svc" = the
# alerting service, "dep" = its dependency); it sets the suspect_component label.
#
# Known limitations (deliberately NOT changed, see CHANGES.md): each archetype has a fixed,
# unique LOGS line that names the cause, variants only swap names/numbers (14 distinct texts),
# and severity 3 coincides exactly with auto_safe=False. Category labels for db_saturation
# ("storage" vs "capacity") and dns_failure ("network" vs "config") are arguable; they were
# left as originally written rather than changed after seeing model outputs.
_ARCHETYPES: list[dict[str, Any]] = [
    dict(name="bad_deploy", category="app", root_cause="bad_deploy", action="rollback",
         sev=2, auto_safe=True, real_incident=True,
         symptom="error rate on {svc} rose sharply right after a deploy",
         metrics="p99 latency 180ms -> 1.9s; 5xx 0.3% -> 12.4%; pods healthy",
         change="{svc} v{fw}.{fw2}.0 deployed 6 min before onset",
         logs="NullPointerException in {handler} line 214"),
    dict(name="config_drift", category="config", root_cause="config_error", action="patch_config",
         sev=2, auto_safe=True, real_incident=True,
         symptom="{svc} rejecting ~40% of requests with schema validation errors",
         metrics="error rate 38%; CPU 22%; no restarts",
         change="config map {svc}-config edited 11 min before onset",
         logs="invalid config key {cfg}: expected integer, got 'null'"),
    dict(name="cpu_saturation", category="capacity", root_cause="resource_exhaustion", action="scale_up",
         sev=2, auto_safe=True, real_incident=True,
         symptom="{svc} latency climbing under steady load",
         metrics="CPU 98%, run-queue depth 41, p99 2.4s, no OOM",
         change="traffic +18% week-over-week; no deploy",
         logs="thread pool exhausted; queue full"),
    dict(name="memory_leak", category="capacity", root_cause="resource_exhaustion", action="restart",
         sev=2, auto_safe=True, real_incident=True,
         symptom="{svc} pods OOMKilling every ~20 min",
         metrics="RSS growing 60MB/min; restarts 7 in 40 min; 5xx 4%",
         change="no recent deploy; gradual since yesterday",
         logs="OOMKilled: container exceeded 2Gi limit"),
    dict(name="dependency_outage", category="network", root_cause="dependency_outage", action="failover",
         sev=3, auto_safe=False, real_incident=True, origin="dep",
         symptom="{svc} timing out calling {dep}",
         metrics="p99 to {dep} 8.5s; {svc} error 19%; {dep} health degraded",
         change="no change on {svc}; {dep} incident opened upstream",
         logs="upstream connect timeout to {dep}:8080"),
    dict(name="network_partition", category="network", root_cause="network_partition", action="failover",
         sev=3, auto_safe=False, real_incident=True, origin="dep",
         symptom="intermittent packet loss between {svc} and {dep}",
         metrics="packet loss 22% on link; retransmits high; cross-AZ only",
         change="no deploy; cloud provider status page reports degraded networking",
         logs="i/o timeout after 3 retries"),
    dict(name="dns_failure", category="network", root_cause="dns_failure", action="patch_config",
         sev=2, auto_safe=True, real_incident=True,
         symptom="{svc} failing to resolve {dep}",
         metrics="DNS NXDOMAIN rate 90%; error 31%; CPU low",
         change="coreDNS configmap edited 9 min before onset",
         logs="no such host {dep}.svc.cluster.local"),
    dict(name="cert_expiry", category="config", root_cause="certificate_expiry", action="patch_config",
         sev=2, auto_safe=True, real_incident=True,
         symptom="TLS handshakes failing at {svc}",
         metrics="TLS errors 100% on new connections; established unaffected",
         change="certificate for {svc} expired 12 min ago",
         logs="x509: certificate has expired or is not yet valid"),
    dict(name="traffic_spike", category="capacity", root_cause="traffic_spike", action="scale_up",
         sev=2, auto_safe=True, real_incident=True,
         symptom="{svc} request rate 5x baseline",
         metrics="RPS 5x; CPU 91%; legitimate UK campaign traffic",
         change="marketing campaign launched; no deploy",
         logs="rate limiter near threshold"),
    dict(name="db_saturation", category="storage", root_cause="resource_exhaustion", action="escalate",
         sev=3, auto_safe=False, real_incident=True, origin="dep", dep="db-primary",
         symptom="{dep} connection pool exhausted",
         metrics="active connections 500/500; queries queued 320; replication lag 40s",
         change="no deploy; slow query introduced by ad-hoc analytics job",
         logs="FATAL: remaining connection slots reserved"),
    dict(name="data_corruption", category="storage", root_cause="data_corruption", action="escalate",
         sev=3, auto_safe=False, real_incident=True, origin="dep", dep="db-primary",
         symptom="order totals inconsistent in {dep}",
         metrics="checksum mismatch on 0.4% of rows; no latency impact",
         change="batch backfill job ran 2h before onset",
         logs="integrity check failed for table orders"),
    dict(name="security_incident", category="security", root_cause="security_incident", action="escalate",
         sev=3, auto_safe=False, real_incident=True,
         symptom="credential stuffing against {svc} from many IPs",
         metrics="401s 30x baseline; 1 account taken over; WAF alerts",
         change="no deploy; source ASN foreign",
         logs="possible account takeover: new device login after 412 failures"),
    dict(name="monitoring_fluke", category="other", root_cause="other", action="observe",
         sev=1, auto_safe=True, real_incident=False,
         symptom="single-sample 5xx blip on {svc}",
         metrics="one 30s bucket at 6% then back to 0.1%; no user reports",
         change="no change; monitoring scrape jitter",
         logs="no errors in application logs"),
    dict(name="planned_maintenance", category="other", root_cause="other", action="observe",
         sev=1, auto_safe=True, real_incident=False,
         symptom="{svc} replicas temporarily reduced",
         metrics="expected during maintenance window; SLI within budget",
         change="scheduled maintenance window; change ticket CHG-{fw2}{fw}",
         logs="pod evicted by node drain (planned)"),
]

_SERVICE_POOL = ["checkout-api", "payment-svc", "auth-svc", "cart-svc", "search-svc"]
_DEP_POOL = ["db-primary", "redis-cache", "payment-svc", "search-svc", "auth-svc"]
# code location named in the bad-deploy stack trace, so the log matches the alerting service
_HANDLERS = {
    "checkout-api": "OrderController.checkout",
    "payment-svc": "PaymentController.capture",
    "auth-svc": "SessionController.refresh",
    "cart-svc": "CartController.addItem",
    "search-svc": "QueryController.search",
}


def _pick_dep(a: dict[str, Any], svc: str, idx: int, v: int) -> str:
    """Archetype's fixed dependency if it has one, else rotate through the pool, never svc."""
    if a.get("dep"):
        return a["dep"]
    for k in range(len(_DEP_POOL)):
        dep = _DEP_POOL[(idx + v + k) % len(_DEP_POOL)]
        if dep != svc:
            return dep
    raise AssertionError("no dependency different from the service")


def _build_state(a: dict[str, Any], svc: str, dep: str, fw: int, fw2: int, cfg: str) -> str:
    def f(s: str) -> str:
        return s.format(svc=svc, dep=dep, fw=fw, fw2=fw2, cfg=cfg, handler=_HANDLERS[svc])
    return (
        f"INCIDENT ALERT\n"
        f"service: {svc}\n"
        f"summary: {f(a['symptom'])}\n\n"
        f"METRICS:\n  {f(a['metrics'])}\n\n"
        f"CHANGES:\n  {f(a['change'])}\n\n"
        f"LOGS:\n  {f(a['logs'])}\n\n"
        f"DEPENDENCIES:\n  {svc} -> {dep}\n"
    )


def generate_corpus(n_variants: int = 4, seed: int = 7) -> list[Incident]:
    """One incident per archetype per variant, with rotating services."""
    rng = random.Random(seed)
    incidents: list[Incident] = []
    idx = 0
    for v in range(n_variants):
        for a in _ARCHETYPES:
            idx += 1
            svc = _SERVICE_POOL[idx % len(_SERVICE_POOL)]
            dep = _pick_dep(a, svc, idx, v)
            fw, fw2 = rng.randint(1, 9), rng.randint(0, 9)
            cfg = rng.choice(["CHECKOUT_TIMEOUT_MS", "PAYMENT_RETRIES", "CACHE_TTL_S", "DNS_RESOLVER"])
            state = _build_state(a, svc, dep, fw, fw2, cfg)
            # the fault's origin: the dependency for dependency/network/database faults
            suspect = dep if a.get("origin") == "dep" else svc
            gt = {
                "real_incident": a["real_incident"],
                "failure_category": a["category"],
                "suspect_component": suspect,
                "root_cause": a["root_cause"],
                "severity": a["sev"],
                "correct_action": a["action"],
                "auto_safe": a["auto_safe"],
            }
            incidents.append(Incident(
                id=f"INC-{idx:04d}",
                archetype=a["name"],
                state=state,
                ground_truth=gt,
                meta={"service": svc, "dependency": dep, "category": a["category"]},
            ))
    return incidents


def corpus_fingerprint(incidents: list[Incident]) -> str:
    """Short hash of every incident's text and labels. Stored in each decision record so
    reports can refuse to mix results scored against different corpus versions."""
    h = hashlib.sha256()
    for i in incidents:
        h.update(json.dumps([i.id, i.archetype, i.state, i.ground_truth], sort_keys=True).encode())
    return h.hexdigest()[:12]


def main() -> None:  # pragma: no cover - quick inspection
    inc = generate_corpus()
    print(f"{len(inc)} incidents; first two:")
    for i in inc[:2]:
        print(json.dumps(i.to_dict(), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
