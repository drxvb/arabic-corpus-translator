#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_terminology_and_trace.py — deterministic Stage A terminology + G3 telemetry eval.

NO live LLM / vendor network calls. Everything below is driven by the offline
toolkit assets (Asset A calque dictionary + Asset G domain terminology) and the
pure in-process InfluenceTrace telemetry recorded inside stage_a_terminology.

Two groups:

  A. Stage A terminology lookup on an EN sentence containing known
     calque-dictionary + Asset G terms. Asserts hit structure (field shapes),
     calque-dictionary DOMAIN filtering (applies_only_in_domain), and
     topic-guard population (context_keywords -> topic_guards_active).

  T. G3 InfluenceTrace: run the Stage A path with the toolkit's
     influence_telemetry attached and assert the term_hint_injected records are
     emitted with the expected fields (asset_id, trigger, stage, asset_version,
     evidence, seq) and that they correspond 1:1 to the Asset G hits.

Run:
    python evals/test_terminology_and_trace.py
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


def _assert(cond: bool, msg: str) -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    return bool(cond)


def main() -> int:
    print("=== arabic-corpus-translator terminology + trace (G3) eval ===\n")
    failures = 0

    # -----------------------------------------------------------------
    # GROUP A — Stage A terminology lookup, hit structure, domain filter,
    # topic-guard. Offline only (Asset A + Asset G).
    # -----------------------------------------------------------------

    # A tech EN sentence that hits BOTH the Asset G paired-terminology list and
    # the Asset A calque dictionary (verbatim, lower/upper insensitive matches).
    tech_text = (
        "The CEO announced new artificial intelligence features for cloud "
        "computing and 5G networks. Email and instant messaging usage is up. "
        "Personalization features are key."
    )
    sa = T.stage_a_terminology(tech_text, "technology")

    if not _assert(isinstance(sa, dict), "stage_a_terminology returns a dict"):
        failures += 1

    # Asset G + Asset A both available on this machine's toolkit.
    if not _assert(sa.get("asset_g_available") is True and sa.get("asset_f_available") is True,
                   "Asset G and Asset F report available"):
        failures += 1

    g_hits = sa.get("asset_g_terminology_hits", [])
    if not _assert(len(g_hits) >= 5,
                   f"Stage A returns >=5 Asset G terminology hits (got {len(g_hits)})"):
        failures += 1

    # Asset G hit field contract: each hit is a structured dict with en/ar +
    # the fixed source tag the translator stamps on every Asset G hint.
    g_fields_ok = all(
        isinstance(h, dict)
        and h.get("en") and h.get("ar")
        and h.get("source") == "asset_g_paired_terminology"
        for h in g_hits
    )
    if not _assert(g_fields_ok,
                   "every Asset G hit has non-empty en/ar and source='asset_g_paired_terminology'"):
        failures += 1

    # Asset A calque hits (term_hints) carry the calque-detector contract fields.
    term_hints = sa.get("term_hints", [])
    if not _assert(sa.get("matched_count", 0) >= 1 and len(term_hints) == sa.get("matched_count"),
                   f"matched_count matches term_hints length (count={sa.get('matched_count')}, "
                   f"hints={len(term_hints)})"):
        failures += 1
    th_fields_ok = all(
        isinstance(h, dict)
        and "en" in h and "natural_ar" in h
        and "ai_default_calque" in h and "confidence" in h
        for h in term_hints
    )
    if not _assert(th_fields_ok,
                   "every calque-dict hint carries en/natural_ar/ai_default_calque/confidence"):
        failures += 1

    # -- DOMAIN FILTERING --------------------------------------------------
    # The calque entry 'fundraising' is applies_only_in_domain
    # ['business', 'tech-software']. The same sentence must surface it under
    # 'business' but NOT under 'news'. Pure dictionary logic, no network.
    fund_text = "The startup launched a major fundraising round this quarter."
    sa_biz = T.stage_a_terminology(fund_text, "business")
    sa_news = T.stage_a_terminology(fund_text, "news")
    en_biz = {h.get("en") for h in sa_biz.get("term_hints", [])}
    en_news = {h.get("en") for h in sa_news.get("term_hints", [])}
    if not _assert("fundraising" in en_biz,
                   f"'fundraising' surfaces in an allowed domain (business): {sorted(en_biz)}"):
        failures += 1
    if not _assert("fundraising" not in en_news,
                   f"'fundraising' is domain-filtered OUT of 'news' (got {sorted(en_news)})"):
        failures += 1

    # -- TOPIC GUARD -------------------------------------------------------
    # 'view (database)' carries context_keywords -> Stage A must list it in
    # topic_guards_active when the bare EN ('view') appears in a tech-data text.
    guard_text = "The database view returns rows. The query and index are tuned."
    sa_data = T.stage_a_terminology(guard_text, "tech-data")
    if not _assert("view (database)" in set(sa_data.get("topic_guards_active", [])),
                   f"context-keyword entry populates topic_guards_active "
                   f"(got {sa_data.get('topic_guards_active')})"):
        failures += 1
    # Topic-guarded entries are a subset of the matched term_hints (a guard only
    # arms for a term that actually matched).
    guarded = set(sa_data.get("topic_guards_active", []))
    matched_en = {h.get("en") for h in sa_data.get("term_hints", [])}
    if not _assert(guarded <= matched_en,
                   "topic_guards_active is a subset of matched term_hints"):
        failures += 1

    # -----------------------------------------------------------------
    # GROUP T — G3 InfluenceTrace telemetry on the Stage A path.
    # stage_a_terminology instantiates a trace via the toolkit's
    # influence_telemetry.InfluenceTrace and records one term_hint_injected
    # per Asset G hit. We read the in-process trace object straight off the
    # returned hints dict (key '_trace'). No serialization round-trip needed,
    # no network.
    # -----------------------------------------------------------------
    trace = sa.get("_trace")
    if not _assert(trace is not None and type(trace).__name__ == "InfluenceTrace",
                   f"Stage A attaches a toolkit InfluenceTrace (_trace) "
                   f"(got {type(trace).__name__ if trace is not None else None})"):
        # Without telemetry we cannot run the rest of GROUP T.
        print("\nFAILED: InfluenceTrace unavailable; cannot run G3 telemetry group")
        return 1

    injected = trace.by_trigger("term_hint_injected")
    if not _assert(len(injected) == len(g_hits),
                   f"one term_hint_injected record per Asset G hit "
                   f"(records={len(injected)}, hits={len(g_hits)})"):
        failures += 1

    # Field contract per the influence_telemetry data model.
    rec_fields_ok = all(
        set(("seq", "asset_id", "asset_version", "trigger", "stage", "evidence")).issubset(r.keys())
        for r in injected
    )
    if not _assert(rec_fields_ok,
                   "every term_hint_injected record has seq/asset_id/asset_version/trigger/stage/evidence"):
        failures += 1

    # asset_id is the domain-keyed Asset G id 'G.technology' for this call.
    if not _assert(all(r.get("asset_id") == "G.technology" for r in injected),
                   "term_hint_injected records carry asset_id='G.technology'"):
        failures += 1

    # trigger + stage are the expected standardized values (not normalized to 'other').
    if not _assert(all(r.get("trigger") == "term_hint_injected" for r in injected),
                   "trigger is the standardized 'term_hint_injected' (no trigger_raw fallback)"):
        failures += 1
    if not _assert(all(r.get("stage") == "A_terminology" for r in injected),
                   "stage is 'A_terminology' on every term_hint_injected record"):
        failures += 1

    # Evidence carries the en/ar pair, and the set of recorded EN terms matches
    # the set of Asset G hit EN terms exactly (telemetry == observable output).
    trace_ens = {r.get("evidence", {}).get("en") for r in injected}
    hit_ens = {h.get("en") for h in g_hits}
    if not _assert(trace_ens == hit_ens,
                   f"trace evidence EN terms equal the Asset G hit EN terms "
                   f"(trace={len(trace_ens)}, hits={len(hit_ens)})"):
        failures += 1

    # seq is a contiguous 0-based ordinal across the whole trace (append-only).
    all_records = trace.as_json()
    seqs = [r.get("seq") for r in all_records]
    if not _assert(seqs == list(range(len(all_records))),
                   f"trace seq is contiguous 0-based ordinal (got {seqs})"):
        failures += 1

    # summary() agrees with the raw records (no over/under-counting).
    summ = trace.summary()
    if not _assert(summ.get("total_influences") == len(all_records)
                   and summ.get("by_trigger", {}).get("term_hint_injected") == len(injected),
                   f"summary() agrees with raw records "
                   f"(total={summ.get('total_influences')}, "
                   f"term_hint_injected={summ.get('by_trigger', {}).get('term_hint_injected')})"):
        failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} test(s)")
        return 1
    print("OK: all terminology + G3 telemetry tests pass (no live LLM/vendor calls).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
