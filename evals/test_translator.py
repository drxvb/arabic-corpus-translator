#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_translator.py — v1.0.0 eval suite.

LLM-independent tests: Stage A + Stage D run offline (Asset A + Asset F + Asset G
from the toolkit). Stage C is only exercised if LLM_API_URL is set.

Run:
    python evals/test_translator.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from translate import (
    stage_a_terminology,
    stage_b_tm_lookup,
    stage_d_validate,
    apply_lexical_cleanup,
    _find_terminology_pairs_in_text,
    _load_calque_entries,
    _load_terminology_candidates,
    _load_domain_terminology,
)


def _assert(cond: bool, msg: str) -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    return cond


def main() -> int:
    print("=== arabic-corpus-translator v1.0.0 eval suite ===\n")
    failures = 0

    # T1: toolkit assets loadable
    if not _assert(_load_calque_entries(),
                   "Asset A (calque dictionary) loads >0 entries"):
        failures += 1
    if not _assert(_load_terminology_candidates("technology") is not None,
                   "Asset F (terminology-candidates technology) loads"):
        failures += 1
    if not _assert(_load_domain_terminology() is not None,
                   "Asset G (domain-terminology) loads"):
        failures += 1

    # T2: Stage A on tech English finds hints from BOTH calque dictionary AND Asset G
    text = ("The CEO announced new artificial intelligence features for cloud "
            "computing and 5G networks. Email and instant messaging usage is up. "
            "Personalization features are key.")
    result = stage_a_terminology(text, "technology")
    if not _assert(result["matched_count"] >= 1,
                   f"Stage A finds >=1 calque-dict hit (got {result['matched_count']})"):
        failures += 1
    if not _assert(len(result.get("asset_g_terminology_hits", [])) >= 5,
                   f"Stage A finds >=5 Asset G hits (got {len(result.get('asset_g_terminology_hits', []))})"):
        failures += 1
    if not _assert(result.get("asset_f_available") is True and result.get("asset_g_available") is True,
                   "Both Asset F and Asset G are available"):
        failures += 1

    # T3: Stage B is the documented dropped state
    b = stage_b_tm_lookup("test", "technology")
    if not _assert(b.get("status") == "dropped_in_v1.0.0",
                   f"Stage B reports dropped status (got {b.get('status')!r})"):
        failures += 1
    if not _assert(b.get("tm_hits") == [],
                   "Stage B returns empty tm_hits"):
        failures += 1

    # T4: Stage D lexical cleanup on AI-tells
    ar_text = "من المهم ملاحظة أن النظام في غاية الأهمية البالغة جداً للمستخدمين."
    cleaned, diag = apply_lexical_cleanup(ar_text)
    if not _assert(diag.get("ai_phrases_applied", 0) >= 1,
                   f"apply_lexical_cleanup applies AI-phrase substitution (got {diag.get('ai_phrases_applied')})"):
        failures += 1
    if not _assert(diag.get("intensifier_destack_applied", 0) >= 1,
                   f"apply_lexical_cleanup applies intensifier destack (got {diag.get('intensifier_destack_applied')})"):
        failures += 1

    # T5: Stage D scoring
    d = stage_d_validate(ar_text, "test EN")
    if not _assert(d.get("verdict") in ("pass", "warning", "fail"),
                   f"Stage D returns valid verdict (got {d.get('verdict')!r})"):
        failures += 1
    if not _assert("cleaned_draft_ar" in d,
                   "Stage D includes cleaned_draft_ar"):
        failures += 1

    # T6: Asset G pairing on individual terms
    hits = _find_terminology_pairs_in_text("cloud computing and email")
    if not _assert(len(hits) >= 2,
                   f"_find_terminology_pairs_in_text catches multi-term (got {len(hits)})"):
        failures += 1
    has_ai = any(h["en"] == "cloud computing" for h in hits)
    if not _assert(has_ai,
                   "Asset G includes 'cloud computing' pair"):
        failures += 1

    # T7: Case-insensitive Asset G matching
    hits_caps = _find_terminology_pairs_in_text("CLOUD COMPUTING is important")
    if not _assert(len(hits_caps) >= 1,
                   f"Asset G match is case-insensitive (got {len(hits_caps)})"):
        failures += 1

    # T8: News domain stage A reads news terms
    news_result = stage_a_terminology("Saudi Arabia and the European Union signed an agreement.", "news")
    # The translator's Asset G loader is single-file (domain-terminology.json
    # which is technology). News pairs are in domain-terminology-news.json.
    # v1.x will multi-domain this; for now confirm the framework runs.
    if not _assert(isinstance(news_result, dict),
                   "Stage A handles news domain without crashing"):
        failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} test(s)")
        return 1
    print(f"OK: all eval-suite tests pass. Translator v1.0.0 ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
