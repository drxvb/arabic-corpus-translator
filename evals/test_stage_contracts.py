#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_stage_contracts.py — deterministic stage-contract eval suite.

Three contract groups, NO live LLM/vendor network calls:

  C. Stage C resilience: route safe_llm_call against an UNREACHABLE endpoint
     (http://127.0.0.1:9/...) and assert it returns a structured failure
     (ok=False, network/timeout/connection error_class, attempts>=2). The
     toolkit's safe_llm_call never raises and never reaches a real vendor —
     127.0.0.1:9 is the "discard" port and refuses instantly.

  G. min_consensus filtering: monkeypatch _load_domain_terminology with a
     SYNTHETIC Asset-G-style payload whose pairs carry n_independent_agree
     values 1/2/3, then assert the translate-side filter in
     _find_terminology_pairs_in_text keeps the right subset at
     min_consensus = 1 / 2 / 3.

  D. Stage D verdict logic on a known-bad AR draft (several ai_default_calque
     forms stacked -> high calque rate -> verdict 'warning' or 'fail').

Run:
    python evals/test_stage_contracts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import translate as T  # noqa: E402

# The toolkit's safe_llm_call ships the resilience contract. Stage C routes
# through it via T._toolkit_safe_llm_call(). We import it directly for the
# unreachable-endpoint resilience assertions (deterministic, no live vendor).
_safe_llm_call = T._toolkit_safe_llm_call()


def _assert(cond: bool, msg: str) -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    return bool(cond)


# Acceptable structured failure classes for an unreachable local endpoint.
# safe_llm_call maps URLError(connection refused) -> "network"; a stalled
# connect -> "timeout". Both are non-vendor, no-data-leaked failures.
_NET_FAIL_CLASSES = {"network", "timeout", "connection", "connect", "unknown"}


def main() -> int:
    print("=== arabic-corpus-translator stage-contract eval suite ===\n")
    failures = 0

    # -----------------------------------------------------------------
    # GROUP C — Stage C resilience against an UNREACHABLE endpoint.
    # NO live vendor call: 127.0.0.1:9 (discard port) refuses immediately.
    # -----------------------------------------------------------------
    if not _assert(_safe_llm_call is not None,
                   "toolkit safe_llm_call is importable (resilience contract present)"):
        # Without the contract we cannot exercise Stage C resilience at all.
        print("\nFAILED: safe_llm_call unavailable; cannot run Stage C resilience group")
        return 1

    # Reset any circuit-breaker state from prior runs in this process so the
    # first call is a genuine network attempt (not a short-circuit).
    try:
        from safe_llm_call import reset_circuit  # type: ignore
        reset_circuit()
    except Exception:
        pass

    unreachable = "http://127.0.0.1:9"  # discard port — guaranteed unroutable as a chat API
    payload = {"model": "test", "messages": [{"role": "user", "content": "ping"}]}
    res = _safe_llm_call(unreachable, "fake-key", payload,
                         timeout=2.0, max_retries=2, retry_backoff_s=0.05)

    if not _assert(res.ok is False,
                   f"safe_llm_call against unreachable endpoint returns ok=False (got ok={res.ok})"):
        failures += 1
    if not _assert(res.error_class in _NET_FAIL_CLASSES,
                   f"error_class is a network/timeout class (got {res.error_class!r})"):
        failures += 1
    if not _assert(isinstance(res.attempts, int) and res.attempts >= 2,
                   f"retried: attempts>=2 (got {res.attempts})"):
        failures += 1
    if not _assert(res.payload is None,
                   f"no payload on failure (got {res.payload!r})"):
        failures += 1
    if not _assert(res.error_detail is not None and len(str(res.error_detail)) > 0,
                   "structured failure carries a human-readable error_detail"):
        failures += 1

    # The Stage C wrapper itself must surface the same structured failure shape
    # (ok=False + error_class) when its underlying LLM call fails. Drive it via
    # the env-var path pointed at the unreachable endpoint — still no live call.
    import os
    os.environ["LLM_API_URL"] = unreachable + "/v1/chat/completions"
    os.environ["LLM_API_KEY"] = "fake-key"
    os.environ["LLM_MODEL"] = "test"
    try:
        from safe_llm_call import reset_circuit  # type: ignore
        reset_circuit()
    except Exception:
        pass
    sc = T.stage_c_llm_draft("hello world", {"matched_count": 0},
                             {"tm_hits": []}, "technology")
    if not _assert(sc.get("ok") is False,
                   f"stage_c_llm_draft surfaces ok=False on unreachable endpoint (got {sc.get('ok')})"):
        failures += 1
    if not _assert(sc.get("error_class") in _NET_FAIL_CLASSES,
                   f"stage_c_llm_draft surfaces a network/timeout error_class (got {sc.get('error_class')!r})"):
        failures += 1

    # -----------------------------------------------------------------
    # GROUP G — min_consensus filtering on a SYNTHETIC Asset-G hit list.
    # Monkeypatch _load_domain_terminology so the real translate-side filter
    # (_find_terminology_pairs_in_text) runs against pairs carrying
    # n_independent_agree = 1 / 2 / 3. No corpus, no network.
    # -----------------------------------------------------------------
    synthetic_pairs = [
        {"en": "alpha widget",   "ar": "أداة ألفا",   "n_independent_agree": 1},
        {"en": "beta gadget",    "ar": "أداة بيتا",    "n_independent_agree": 2},
        {"en": "gamma module",   "ar": "وحدة جاما",    "n_independent_agree": 3},
        {"en": "delta service",  "ar": "خدمة دلتا",    "n_independent_agree": 2},
        # A pair MISSING the field — must always pass through (backward compat).
        {"en": "legacy term",    "ar": "مصطلح قديم"},
    ]
    by_en = {p["en"].strip().lower(): p for p in synthetic_pairs}
    synthetic_asset = {"$schema_version": "1.10.0", "pairs": synthetic_pairs, "_by_en": by_en}

    # Text that mentions every synthetic EN term verbatim.
    g_text = ("This product is an alpha widget, a beta gadget, a gamma module, "
              "a delta service, and a legacy term in one.")

    _orig_loader = T._load_domain_terminology
    T._load_domain_terminology = lambda domain="technology": synthetic_asset
    try:
        def ens_at(mc):
            return {h["en"] for h in T._find_terminology_pairs_in_text(g_text, "technology", min_consensus=mc)}

        ens1 = ens_at(1)
        ens2 = ens_at(2)
        ens3 = ens_at(3)
    finally:
        T._load_domain_terminology = _orig_loader

    # min_consensus=1: everything with n>=1, PLUS the field-less pair.
    expected1 = {"alpha widget", "beta gadget", "gamma module", "delta service", "legacy term"}
    if not _assert(ens1 == expected1,
                   f"min_consensus=1 keeps all (incl. field-less) pairs (got {sorted(ens1)})"):
        failures += 1

    # min_consensus=2: drop the n=1 alpha; keep n>=2 and the field-less pair.
    expected2 = {"beta gadget", "gamma module", "delta service", "legacy term"}
    if not _assert(ens2 == expected2,
                   f"min_consensus=2 drops n=1 only (got {sorted(ens2)})"):
        failures += 1

    # min_consensus=3: only the unanimous gamma (n=3) and the field-less pair.
    expected3 = {"gamma module", "legacy term"}
    if not _assert(ens3 == expected3,
                   f"min_consensus=3 keeps only n=3 + field-less (got {sorted(ens3)})"):
        failures += 1

    # Monotonicity: tightening consensus is a strict superset->subset chain.
    if not _assert(ens3 <= ens2 <= ens1,
                   "filtering is monotone: ens3 ⊆ ens2 ⊆ ens1"):
        failures += 1

    # The field-less pair must survive every tier (backward compatibility).
    if not _assert("legacy term" in ens1 and "legacy term" in ens2 and "legacy term" in ens3,
                   "pair missing n_independent_agree passes through at every min_consensus tier"):
        failures += 1

    # -----------------------------------------------------------------
    # GROUP D — Stage D verdict logic on a KNOWN-BAD AR draft.
    # Stack multiple ai_default_calque forms from the real calque dictionary so
    # the calque rate is high and term_fidelity is low -> verdict 'warning'/'fail'.
    # NO LLM: we feed the draft string straight into stage_d_validate.
    # -----------------------------------------------------------------
    entries = T._load_calque_entries()
    if not _assert(bool(entries),
                   "calque dictionary loads (Stage D detector available)"):
        failures += 1

    # Pull several distinct ai_default_calque strings straight from the dict so
    # the test stays in sync with the real detector vocabulary.
    calques = []
    seen = set()
    for e in entries:
        c = (e.get("ai_default_calque") or "").strip()
        if c and c not in seen:
            seen.add(c)
            calques.append(c)
        if len(calques) >= 6:
            break

    # Build a short draft (few tokens) saturated with calque forms -> high
    # calque_rate_per_1k_tokens AND zero natural-form hits -> term_fidelity 0.0.
    bad_ar = "النظام يستخدم " + " و ".join(calques) + " فقط."
    d = T.stage_d_validate(bad_ar, "the system uses these terms only")

    if not _assert(d.get("verdict") in ("pass", "warning", "fail"),
                   f"Stage D returns a valid verdict (got {d.get('verdict')!r})"):
        failures += 1
    if not _assert(d.get("calque_count", 0) >= 3,
                   f"Stage D detects the stacked calques (calque_count={d.get('calque_count')})"):
        failures += 1
    if not _assert(d.get("verdict") in ("warning", "fail"),
                   f"known-bad calque-heavy draft is NOT a pass (got {d.get('verdict')!r}, "
                   f"calque_rate={d.get('calque_rate_per_1k_tokens')}, "
                   f"term_fidelity={d.get('term_fidelity')})"):
        failures += 1
    if not _assert(d.get("calque_rate_per_1k_tokens") is not None
                   and d.get("calque_rate_per_1k_tokens") > 3.0,
                   f"calque_rate exceeds the warning ceiling (got {d.get('calque_rate_per_1k_tokens')})"):
        failures += 1
    if not _assert("cleaned_draft_ar" in d,
                   "Stage D result includes cleaned_draft_ar"):
        failures += 1

    # Contrast control: a clean, calque-free MSA sentence must NOT 'fail'.
    clean_ar = "أعلنت الشركة عن نتائجها المالية للربع الأخير من العام."
    dc = T.stage_d_validate(clean_ar, "the company announced its Q4 results")
    if not _assert(dc.get("verdict") in ("pass", "warning"),
                   f"clean calque-free draft is not a 'fail' (got {dc.get('verdict')!r})"):
        failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} test(s)")
        return 1
    print("OK: all stage-contract tests pass (no live LLM/vendor calls).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
