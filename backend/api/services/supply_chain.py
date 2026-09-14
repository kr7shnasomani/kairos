"""
Model supply-chain integrity — `ARCHITECTURE.md §8` anti-poisoning mitigations 1 and 3.

The section names three. This module implements two; the third (parameter anomaly detection
against per-equipment-class historical distributions) needs a distribution this corpus cannot
supply and stays recorded as a known limitation rather than half-built.

WHY "MODEL WEIGHT SIGNING" IS NOT WHAT THIS DOES
  The architecture asks for "cryptographic signing of all model weight files at source". Kairos
  runs **no local weights** — inference is NIM, Jina and Groq over HTTPS, so there is no artifact
  in its custody to sign, and a signature it generated itself would attest to nothing.

  The real supply-chain exposure for a hosted model is different and, until now, unmonitored: the
  provider silently serving a *different model* than the one configured. That is exactly the
  substitution signing is meant to catch, and it is detectable — an OpenAI-compatible response
  echoes the model that produced it. `verify_served_model` compares that against the pin.

  This matters beyond security. Every benchmark figure attributed to a named model rests on the
  assumption that the pinned model answered. Until NVIDIA retired `llama-3.1-70b` (2026-09-13), NIM and
  OpenRouter both served it; tier 1 is now Nemotron, so a fallthrough always changes the model.
"""

import statistics
from collections import Counter
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Below this, "unusual" is not a statistical statement. With three submitting accounts the most
# active one is always the outlier by some measure, and flagging it is noise that trains a
# reviewer to ignore the signal.
_MIN_ACCOUNTS_FOR_OUTLIER = 5

# A submitter is flagged at this multiple of the median. Median, not mean: one bulk-import
# account would drag a mean far enough that nothing ever clears it.
_OUTLIER_MEDIAN_MULTIPLE = 4.0


def verify_served_model(configured: str, response: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compare the model a provider says it ran against the one that was pinned.

    Returns a mismatch record, or `None` when they agree or the provider did not say.

    A missing `model` field is deliberately **not** a mismatch: some providers omit it, and
    treating silence as substitution would fire on every one of them and get the check disabled.
    Absence is reported by the caller as `unverified`, which is honest — it is the difference
    between "checked and matched" and "could not check".
    """
    served = (response or {}).get("model")
    if not served or not configured:
        return None
    if served == configured:
        return None

    # Providers routinely qualify a pin: "meta/llama-3.1-70b-instruct" served as
    # "meta/llama-3.1-70b-instruct-turbo", or namespaced differently. Treat a containment match
    # as the same family and report it separately — flagging it as substitution would be a false
    # positive, but silently accepting it would hide a quantised or distilled variant.
    a, b = served.lower(), configured.lower()
    related = a in b or b in a

    record = {
        "configured": configured,
        "served": served,
        "severity": "variant" if related else "substitution",
    }
    log.warning(
        "supply_chain.model_mismatch",
        configured=configured,
        served=served,
        severity=record["severity"],
    )
    return record


def submission_pattern_outliers(
    submitters: list[str],
    *,
    min_accounts: int = _MIN_ACCOUNTS_FOR_OUTLIER,
    multiple: float = _OUTLIER_MEDIAN_MULTIPLE,
) -> dict[str, Any]:
    """Accounts submitting documents at an unusual rate — mitigation 3.

    Poisoning through ingestion needs volume: a single falsified document is what the human
    promotion gate is for, but a source account quietly submitting far more than its peers is the
    pattern that gate cannot see, because it reviews documents one at a time.

    Reports, never blocks. A legitimate bulk import looks identical to an attack from here — the
    output is a prompt for a human to ask why, not a verdict.

    Deliberately conservative: below `min_accounts` it returns no flags at all rather than a
    weaker signal, because with a handful of accounts the busiest is trivially the "outlier" and
    a check that always fires is one nobody reads.
    """
    counts = Counter(s for s in submitters if s)
    total = sum(counts.values())
    if len(counts) < min_accounts:
        return {
            "flagged": [],
            "accounts": len(counts),
            "total_submissions": total,
            "verdict": "insufficient_accounts",
            "note": (
                f"{len(counts)} submitting account(s); at least {min_accounts} are needed before "
                "'unusual' is a statistical statement rather than a description of the busiest one."
            ),
        }

    median = statistics.median(counts.values())
    threshold = max(median * multiple, median + 1)
    flagged = [
        {"submitted_by": who, "count": n, "median": median, "threshold": round(threshold, 2)}
        for who, n in counts.most_common()
        if n > threshold
    ]
    if flagged:
        log.warning(
            "supply_chain.submission_outliers",
            flagged=[f["submitted_by"] for f in flagged],
            median=median,
        )
    return {
        "flagged": flagged,
        "accounts": len(counts),
        "total_submissions": total,
        "median_per_account": median,
        "threshold": round(threshold, 2),
        "verdict": "outliers_found" if flagged else "clean",
    }
