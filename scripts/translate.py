#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate.py — CLI for arabic-corpus-translator v0.1.

v0.1 ships Stage A (terminology lookup) + Stage C (LLM draft, stubbed)
with Stage B (Translation Memory) and Stage D (Validator) deferred to
v0.2. The CLI shape is fixed in v0.1 so consumers can wire up the
invocation pattern without waiting for the full pipeline.

Usage (current — v0.1):
    python translate.py --input article-en.md --domain news --output article-ar.md
    python translate.py --analyze --input article-en.md --domain news

Usage (planned — v0.2):
    python translate.py --input article-en.md --domain news --strict --output article-ar.md
                                                             # ^^^ fails if validator rejects

Python 3 stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Toolkit resolution: prefer ARABIC_CORPUS_TOOLKIT_ROOT env var, then sibling
# directory `../arabic-corpus-toolkit`. Same pattern as humanizer v2.7.0.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLKIT_DEFAULT = _REPO_ROOT.parent / "arabic-corpus-toolkit"


def _toolkit_root() -> Optional[Path]:
    override = os.environ.get("ARABIC_CORPUS_TOOLKIT_ROOT")
    candidates: List[Path] = []
    if override:
        candidates.append(Path(override))
    candidates.append(_TOOLKIT_DEFAULT)
    for c in candidates:
        if (c / "corpus" / "calque-dictionary.json").exists():
            return c
    return None


def stage_a_terminology(text_en: str, domain: str) -> Dict[str, Any]:
    """Stage A: look up known calque corrections from the toolkit.

    Returns a hint object the LLM can use:
      {
        "term_hints": [{"en": "...", "natural_ar": "...", "domain": "...", "confidence": "..."}],
        "topic_guards_active": [...],
        "matched_count": int
      }
    v0.1: rudimentary lookup. v0.2 will integrate context_keywords gating
    and exclude_if_pattern logic from the toolkit's lookup engine.
    """
    tk = _toolkit_root()
    hints: Dict[str, Any] = {"term_hints": [], "topic_guards_active": [], "matched_count": 0}
    if tk is None:
        hints["warning"] = "toolkit not found; Stage A returned empty hints"
        return hints

    dict_path = tk / "corpus" / "calque-dictionary.json"
    try:
        data = json.loads(dict_path.read_text(encoding="utf-8"))
    except Exception as e:
        hints["error"] = f"toolkit dictionary unreadable: {e}"
        return hints

    entries = data.get("entries", []) if isinstance(data, dict) else data
    text_lower = text_en.lower()
    for e in entries:
        en = e.get("en", "")
        if not en:
            continue
        # Strip parenthetical disambiguation (e.g., "view (database)" -> "view")
        bare_en = en.split("(")[0].strip().lower()
        if not bare_en:
            continue
        if bare_en in text_lower:
            entry_domain = e.get("domain", "")
            # Domain filter: if the entry's applies_only_in_domain is set,
            # only fire if the user's domain matches.
            allowed_domains = e.get("applies_only_in_domain", [])
            if allowed_domains and domain not in allowed_domains:
                continue
            hints["term_hints"].append({
                "en": en,
                "natural_ar": e.get("natural_arabic", ""),
                "ai_default_calque": e.get("ai_default_calque", ""),
                "domain": entry_domain,
                "confidence": e.get("confidence", ""),
                "political_sensitivity": e.get("political_sensitivity"),
                "disambiguation_warning": e.get("disambiguation_warning"),
            })
            if e.get("context_keywords_arabic") or e.get("context_keywords_english"):
                hints["topic_guards_active"].append(en)
            hints["matched_count"] += 1
    return hints


def stage_b_tm_lookup(text_en: str, domain: str) -> Dict[str, Any]:
    """Stage B: Translation Memory fuzzy-match (v0.2+).

    v0.1 stub. v0.2 will:
      1. Index Y:\\Linguistics\\NewsDataForTranslation\\_corpus\\parallel\\ into
         a SQLite FTS5 table with EN and AR columns linked by UUID
      2. For each input sentence, retrieve the top-K nearest EN matches
      3. Return EN→AR pairs with similarity score; ≥0.85 = "use directly";
         0.70-0.85 = "include as LLM hint"; <0.70 = "no useful match"
    """
    return {
        "tm_hits": [],
        "stub_version": "v0.1",
        "note": "Stage B is a stub. Translation Memory mining lands in v0.2.",
    }


def stage_c_llm_draft(text_en: str, term_hints: Dict[str, Any],
                      tm_hints: Dict[str, Any], domain: str) -> Dict[str, Any]:
    """Stage C: LLM draft using terminology + TM hints (v0.1 stub).

    v0.1 returns a placeholder. v0.2 will invoke the configured LLM
    endpoint via `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL` env vars
    (same pattern as `arabic-ai-text-humanizer`).
    """
    return {
        "draft_ar": "[STUB OUTPUT — Stage C LLM integration ships in v0.2]",
        "input_en_preview": text_en[:200],
        "term_hints_count": term_hints.get("matched_count", 0),
        "tm_hits_count": len(tm_hints.get("tm_hits", [])),
        "domain": domain,
        "stub_version": "v0.1",
    }


def stage_d_validate(draft_ar: str, source_en: str) -> Dict[str, Any]:
    """Stage D: validator (v0.2+).

    v0.1 stub. v0.2 will implement the three metrics from Agent B's design:
      - calque_rate: how many natural_arabic entries from the dict appear in draft
        (higher is better; if their ai_default_calque appears instead, that's a hit)
      - term_fidelity: % of in-domain terms matching natural_arabic
      - n_gram_naturalness: corpus-LM perplexity vs `empirical-patterns.json`
        connector distributions
    """
    return {
        "calque_rate": None,
        "term_fidelity": None,
        "n_gram_naturalness": None,
        "verdict": "stub",
        "stub_version": "v0.1",
        "note": "Stage D validator + regen loop lands in v0.2.",
    }


def translate(text_en: str, domain: str, strict: bool = False) -> Dict[str, Any]:
    """Full pipeline. v0.1: Stages A + B (stub) + C (stub) + D (stub)."""
    stage_a = stage_a_terminology(text_en, domain)
    stage_b = stage_b_tm_lookup(text_en, domain)
    stage_c = stage_c_llm_draft(text_en, stage_a, stage_b, domain)
    stage_d = stage_d_validate(stage_c["draft_ar"], text_en)
    return {
        "translator_version": "0.1.0",
        "domain": domain,
        "stages": {
            "A_terminology": stage_a,
            "B_tm_lookup": stage_b,
            "C_llm_draft": stage_c,
            "D_validator": stage_d,
        },
        "output_ar": stage_c["draft_ar"],
        "strict_mode": strict,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="arabic-corpus-translator v0.1")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", help="EN text file to translate")
    src.add_argument("--text", "-t", help="EN text inline")
    p.add_argument("--domain", "-d", default="news",
                   help="Domain hint (news / opinion / business / tech-software / ...). Default: news.")
    p.add_argument("--output", "-o", help="Write AR output to this file")
    p.add_argument("--analyze", action="store_true",
                   help="Stage A only — list term hints without translating")
    p.add_argument("--strict", action="store_true",
                   help="(v0.2) Fail if Stage D validator rejects the draft")
    p.add_argument("--json", action="store_true", help="Emit full pipeline result as JSON")

    args = p.parse_args()
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = args.text

    if args.analyze:
        result = stage_a_terminology(text, args.domain)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = translate(text, args.domain, strict=args.strict)
    if args.output:
        Path(args.output).write_text(result["output_ar"], encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["output_ar"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
