#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate.py — CLI for arabic-corpus-translator.

v0.2 (Option B per references/04-corpus-reality-check.md):
Ships a working 3-STAGE pipeline:
  A. Terminology lookup from arabic-corpus-toolkit (real, v0.1)
  C. LLM draft via OpenAI-compatible endpoint (real, v0.2)
  D. Calque-rate validator (real, v0.2 — uses toolkit dict as detector)

Stage B (Translation Memory) remains deferred. The corpus diagnostic
showed Y:\\Linguistics\\NewsDataForTranslation contains 0 paired
directories; TM-from-aligned-pairs cannot be built from that data.
v0.3+ will implement Option A (title-similarity alignment) if it
proves viable.

Usage:
    # Set LLM endpoint env vars (any OpenAI-compatible API):
    export LLM_API_URL=https://api.openai.com/v1/chat/completions
    export LLM_API_KEY=sk-...
    export LLM_MODEL=gpt-4o-mini

    python translate.py --input article-en.md --domain news --output article-ar.md

    # Analyze-only — show term hints + LLM-free dry run
    python translate.py --analyze --input article-en.md --domain news

    # Strict mode: fail if validator rejects (calque rate > threshold)
    python translate.py --strict --input article-en.md --domain news --output out.md

Python 3 stdlib only (urllib.request for HTTP).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLKIT_DEFAULT = _REPO_ROOT.parent / "arabic-corpus-toolkit"


# ---------------------------------------------------------------------------
# Toolkit resolution
# ---------------------------------------------------------------------------

def _toolkit_disabled() -> bool:
    """v0.2.3: explicit kill-switch matching humanizer v2.7.2 semantics.

    Set ARABIC_CORPUS_TOOLKIT_DISABLE=1 (the literal string '1', not 'true'
    or 'yes') to skip toolkit loading. Stage A returns empty term hints,
    Stage D returns 'skipped (toolkit not found)', Stage C runs normally.
    Useful for isolating the toolkit's contribution when debugging output
    differences. Strict literal match -- DEBUG=1 convention.
    """
    return os.environ.get("ARABIC_CORPUS_TOOLKIT_DISABLE") == "1"


def _toolkit_root() -> Optional[Path]:
    if _toolkit_disabled():
        return None
    override = os.environ.get("ARABIC_CORPUS_TOOLKIT_ROOT")
    candidates: List[Path] = []
    if override:
        candidates.append(Path(override))
    candidates.append(_TOOLKIT_DEFAULT)
    for c in candidates:
        if (c / "corpus" / "calque-dictionary.json").exists():
            return c
    return None


def _load_calque_entries() -> List[Dict[str, Any]]:
    tk = _toolkit_root()
    if tk is None:
        return []
    p = tk / "corpus" / "calque-dictionary.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data.get("entries", []) if isinstance(data, dict) else data


# v0.3.0: Asset F (terminology candidates from toolkit v0.8+) -- consumed as
# a CORPUS-CONFIRMATION signal for Stage A's calque-dictionary recommendations.
# When the AR translation a calque entry suggests appears in the corpus-mined
# terminology candidates, stamp the hint with corpus_confirmed=true. This is
# the trust-signal pattern: don't inject Phase-1 candidates (no EN side) into
# the LLM prompt directly -- use them to upgrade the confidence of dictionary
# hits.
_terminology_cache: Dict[str, Optional[Dict[str, Any]]] = {}


def _load_terminology_candidates(domain: str) -> Optional[Dict[str, Any]]:
    """Load Asset F (Phase 1 candidates) for the given domain. Returns None
    if the toolkit isn't available, the asset doesn't exist for this domain,
    or the schema major version is incompatible. mtime-keyed via the cache."""
    if domain in _terminology_cache:
        cached = _terminology_cache[domain]
        # Quick re-check: if cached, verify file mtime hasn't advanced
        if cached is not None:
            tk = _toolkit_root()
            if tk is None:
                _terminology_cache[domain] = None
                return None
            p = tk / "corpus" / f"terminology-candidates-{domain}.json"
            if p.exists() and p.stat().st_mtime == cached.get("_cached_mtime"):
                return cached
        else:
            return None

    tk = _toolkit_root()
    if tk is None:
        _terminology_cache[domain] = None
        return None
    p = tk / "corpus" / f"terminology-candidates-{domain}.json"
    if not p.exists():
        _terminology_cache[domain] = None
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        _terminology_cache[domain] = None
        return None
    schema_major = data.get("$schema_version", "0.0.0").split(".")[0]
    if schema_major != "1":
        _terminology_cache[domain] = None
        return None
    # Build a frequency-keyed lookup for O(1) term-presence checks
    by_term: Dict[str, int] = {}
    for c in data.get("candidates", []):
        term = c.get("term_ar", "")
        if term:
            by_term[term] = c.get("freq", 0)
    data["_by_term"] = by_term
    data["_cached_mtime"] = p.stat().st_mtime
    _terminology_cache[domain] = data
    return data


def _corpus_confirm(term_ar: str, domain: str) -> Optional[Tuple[bool, int]]:
    """Check if term_ar appears in the Asset F candidates for the given domain.
    Returns (confirmed_bool, freq) or None if Asset F is not available for this domain."""
    data = _load_terminology_candidates(domain)
    if data is None:
        return None
    by_term = data.get("_by_term", {})
    if term_ar in by_term:
        return (True, by_term[term_ar])
    return (False, 0)


# v0.3.1: Asset G (domain-terminology paired EN<->AR terms from toolkit v0.9+).
# v1.0.1: multi-domain support. Loader keys by domain; technology and news both
# supported. Domain-specific file path: domain-terminology.json (technology,
# default) or domain-terminology-news.json (news).
_domain_terminology_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_domain_terminology_mtime: Dict[str, Optional[float]] = {}


def _domain_terminology_path(tk_root, domain: str) -> Path:
    """Map domain -> filename. Technology uses the canonical name; other
    domains use a -<domain> suffix."""
    if domain == "technology":
        return tk_root / "corpus" / "domain-terminology.json"
    return tk_root / "corpus" / f"domain-terminology-{domain}.json"


def _load_domain_terminology(domain: str = "technology") -> Optional[Dict[str, Any]]:
    """Load Asset G for the given domain. Returns None if toolkit not present,
    asset missing, or schema MAJOR version incompatible. Cache keyed by domain.

    v1.0.1: multi-domain. Technology and news supported.
    """
    if domain in _domain_terminology_cache and _domain_terminology_cache[domain] is not None:
        cached_mtime = _domain_terminology_mtime.get(domain)
        if cached_mtime is not None:
            tk = _toolkit_root()
            if tk is not None:
                p = _domain_terminology_path(tk, domain)
                if p.exists() and p.stat().st_mtime == cached_mtime:
                    return _domain_terminology_cache[domain]
    tk = _toolkit_root()
    if tk is None:
        _domain_terminology_cache[domain] = None
        return None
    p = _domain_terminology_path(tk, domain)
    if not p.exists():
        _domain_terminology_cache[domain] = None
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        _domain_terminology_cache[domain] = None
        return None
    schema_major = data.get("$schema_version", "0.0.0").split(".")[0]
    if schema_major != "1":
        _domain_terminology_cache[domain] = None
        return None
    by_en: Dict[str, Dict[str, Any]] = {}
    for pair in data.get("pairs", []):
        en = pair.get("en", "").strip().lower()
        if en:
            by_en[en] = pair
    data["_by_en"] = by_en
    _domain_terminology_cache[domain] = data
    _domain_terminology_mtime[domain] = p.stat().st_mtime
    return data


def _find_terminology_pairs_in_text(text_en: str, domain: str = "technology") -> List[Dict[str, Any]]:
    """Whole-word EN match against Asset G for the given domain.
    v1.0.1: domain-keyed."""
    data = _load_domain_terminology(domain)
    if data is None or not text_en:
        return []
    text_lower = text_en.lower()
    by_en = data.get("_by_en", {})
    hits: List[Dict[str, Any]] = []
    seen: set = set()
    sorted_ens = sorted(by_en.keys(), key=len, reverse=True)
    for en in sorted_ens:
        if en in seen:
            continue
        pattern = r"\b" + re.escape(en) + r"\b"
        if re.search(pattern, text_lower):
            hits.append(by_en[en])
            seen.add(en)
    return hits


# v0.2.2: Asset C (lexical-tables) integration. Loader + projection mirror the
# humanizer's v2.7.1 cutover. The translator applies a CONSERVATIVE subset of
# Asset C in Stage D: only deterministic substitutions (ai_phrases + intensifier
# de-stack). Probabilistic / variance-introducing tables (connectors with
# probability 0.7, quote-verb rotation, repetitive-starter detection, intensity-
# gated fillers) are deliberately NOT applied — the translator's contract is
# reproducibility, not the humanizer's "introduce variance for humanness."

def _load_lexical_tables_from_toolkit() -> Optional[Dict[str, Any]]:
    """Read Asset C from the toolkit. Returns None on any failure
    (file missing, parse error, schema-major mismatch)."""
    tk = _toolkit_root()
    if tk is None:
        return None
    # Toolkit may be present (calque-dictionary.json) but Asset C may be older
    # — Asset C only shipped in toolkit v0.7+. Check explicitly.
    p = tk / "corpus" / "lexical-tables.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    schema_major = data.get("$schema_version", "0.0.0").split(".")[0]
    if schema_major != "1":
        return None  # incompatible MAJOR version
    return data


def apply_lexical_cleanup(text_ar: str) -> Tuple[str, Dict[str, int]]:
    """Apply the deterministic subset of Asset C to a translated draft.

    Applies:
      - ai_phrases: substitute with the FIRST non-empty alternative (deterministic
        — no random choice. If all alternatives are empty, deletes the phrase).
      - intensifier_destack: regex substitution for stacked intensifiers.

    Skips: connectors (probabilistic), quote_verbs (rotation), repetitive_starters
    (consecutive-trigger needs sentence-pair tracking), fillers (intensity-gated
    is humanizer-specific), structural_openers (regex capture+template risks
    over-substitution in translation context).

    Returns (cleaned_text, diagnostics_dict).
    """
    data = _load_lexical_tables_from_toolkit()
    diag: Dict[str, int] = {
        "ai_phrases_applied": 0,
        "intensifier_destack_applied": 0,
        "asset_available": 0,
    }
    if data is None:
        return text_ar, diag
    diag["asset_available"] = 1
    tables = data.get("tables", {})

    # ai_phrases: longest-key-first to avoid sub-string interference
    # (e.g. "من المهم ملاحظة أن" must match before bare "من المهم ملاحظة").
    ai_entries = tables.get("ai_phrases", {}).get("entries", [])
    sorted_ai = sorted(ai_entries, key=lambda e: len(e.get("input", "")), reverse=True)
    for entry in sorted_ai:
        needle = entry.get("input", "")
        alternatives = entry.get("alternatives", [])
        if not needle or not alternatives:
            continue
        # Deterministic choice: first non-empty alternative, else empty (delete)
        replacement = next((a for a in alternatives if a), "")
        if needle in text_ar:
            count = text_ar.count(needle)
            text_ar = text_ar.replace(needle, replacement)
            diag["ai_phrases_applied"] += count

    # intensifier_destack: regex patterns, applied in declaration order
    destack_entries = tables.get("intensifier_destack", {}).get("entries", [])
    for entry in destack_entries:
        pattern = entry.get("pattern", "")
        replacement = entry.get("replacement", "")
        if not pattern:
            continue
        try:
            new_text, n = re.subn(pattern, replacement, text_ar)
            if n:
                text_ar = new_text
                diag["intensifier_destack_applied"] += n
        except re.error:
            continue

    return text_ar, diag


# ---------------------------------------------------------------------------
# Stage A — Terminology
# ---------------------------------------------------------------------------

def stage_a_terminology(text_en: str, domain: str) -> Dict[str, Any]:
    """Look up known calque corrections from the toolkit. Returns LLM-prompt-ready hints.

    v0.3.0: each hint also carries a corpus_confirmed field via Asset F lookup.
    When the suggested natural_ar form is attested in the Phase-1 terminology
    candidates for this domain (e.g., 'الذكاء الاصطناعي' in the AITNews-mined
    technology candidates), corpus_confirmed=true and corpus_freq carries the
    AITNews frequency. This upgrades dictionary recommendations from
    'dictionary-only' to 'dictionary + corpus-attested.' Hints without corpus
    confirmation still ship -- they're just flagged for the LLM with lower
    weight signal.
    """
    hints: Dict[str, Any] = {
        "term_hints": [],
        "topic_guards_active": [],
        "matched_count": 0,
        "asset_f_available": _load_terminology_candidates(domain) is not None,
        "asset_g_available": _load_domain_terminology(domain) is not None,
        "asset_g_terminology_hits": [],
    }
    # v0.3.1: scan input EN text for direct Asset G pairs first.
    # v1.0.1: domain-aware -- uses technology pairs for --domain technology,
    # news pairs for --domain news, etc.
    g_hits = _find_terminology_pairs_in_text(text_en, domain)
    for pair in g_hits:
        hints["asset_g_terminology_hits"].append({
            "en": pair.get("en"),
            "ar": pair.get("ar"),
            "corpus_freq": pair.get("corpus_freq"),
            "confidence": pair.get("confidence"),
            "proposer": pair.get("proposer"),
            "source": "asset_g_paired_terminology",
        })

    entries = _load_calque_entries()
    if not entries:
        hints["warning"] = "toolkit not found OR dictionary empty"
        return hints

    text_lower = text_en.lower()
    n_corpus_confirmed = 0
    for e in entries:
        en = e.get("en", "")
        if not en:
            continue
        bare_en = en.split("(")[0].strip().lower()
        if not bare_en or bare_en not in text_lower:
            continue
        allowed_domains = e.get("applies_only_in_domain", [])
        if allowed_domains and domain not in allowed_domains:
            continue
        natural_ar = e.get("natural_arabic", "")
        confirm = _corpus_confirm(natural_ar, domain) if natural_ar else None
        hint = {
            "en": en,
            "natural_ar": natural_ar,
            "ai_default_calque": e.get("ai_default_calque", ""),
            "domain": e.get("domain", ""),
            "confidence": e.get("confidence", ""),
            "political_sensitivity": e.get("political_sensitivity"),
            "disambiguation_warning": e.get("disambiguation_warning"),
        }
        if confirm is not None:
            hint["corpus_confirmed"] = confirm[0]
            hint["corpus_freq"] = confirm[1]
            if confirm[0]:
                n_corpus_confirmed += 1
        hints["term_hints"].append(hint)
        if e.get("context_keywords_arabic") or e.get("context_keywords_english"):
            hints["topic_guards_active"].append(en)
        hints["matched_count"] += 1
    hints["corpus_confirmed_count"] = n_corpus_confirmed
    return hints


# ---------------------------------------------------------------------------
# Stage C — LLM Draft (v0.2 — real implementation)
# ---------------------------------------------------------------------------

def _build_llm_prompt(text_en: str, term_hints: Dict[str, Any], domain: str) -> Tuple[str, str]:
    """Return (system_prompt, user_prompt)."""
    # Build a terminology table the LLM can consult.
    term_lines: List[str] = []
    for h in term_hints.get("term_hints", [])[:50]:  # cap at 50 to keep prompt size reasonable
        warning = ""
        if h.get("political_sensitivity") in ("high", "critical"):
            warning = f" ⚠ POLITICAL SENSITIVITY: {h.get('disambiguation_warning', '')[:200]}"
        term_lines.append(
            f"- '{h['en']}' → '{h['natural_ar']}' "
            f"(natural; avoid the AI-default calque '{h.get('ai_default_calque', '?')}'){warning}"
        )
    term_block = "\n".join(term_lines) if term_lines else "(no terminology hits)"

    system_prompt = (
        "You are an Arabic translator producing modern MSA prose for the news/editorial register. "
        "Strict requirements:\n"
        "1. Translate to Modern Standard Arabic (MSA). No dialect.\n"
        "2. Honor the terminology table EXACTLY — use the natural-Arabic forms, NEVER the AI-default calques.\n"
        "3. Respect political-sensitivity warnings — if an entry is flagged HIGH/CRITICAL, do NOT use the AI default.\n"
        "4. Output ONLY the Arabic translation — no commentary, no markdown wrappers, no preamble.\n"
        "5. Preserve the source's paragraph structure.\n"
        "6. Use Arabic punctuation (، ؛ ؟) in Arabic sentences, not Latin (, ; ?).\n"
        f"Domain hint: {domain}."
    )

    user_prompt = (
        f"# Terminology table (use these forms verbatim):\n{term_block}\n\n"
        f"# Source text (English):\n{text_en}\n\n"
        f"# Translate to Arabic:"
    )
    return system_prompt, user_prompt


# v1.1.0: cross-vendor translation review. After Stage C produces a draft,
# the review function sends source + draft to a SECOND proxy and asks "does the
# AR translation correctly render the EN source? Are any terminology hits
# missing or incorrect?" The reviewer returns a verdict + any specific
# corrections it spotted. This catches single-LLM hallucinations (e.g., the
# end-to-end demo's instant-messaging-as-travel typo).
#
# Uses the LAN proxy fleet documented in
# M:\Main\DevTools\AI\config\llm-proxies.md.
_REVIEW_PROXIES = {
    "kimi":    {"url": "http://192.168.80.107:11435", "key": "U6hI7j57HpRpz9QaafTJLsJw5PlTXtxBM4pVNTknohE", "model": "kimi-cli"},
    "codex":   {"url": "http://192.168.80.107:11436", "key": "VJyi6yQDhEGNDE999FkHTqBAG21KdzmW",     "model": "gpt-5.5"},
    "gemini":  {"url": "http://192.168.80.107:11437", "key": "6fjc4jGwIhXQn7NejizvFVKR7Ps1SXES",     "model": "gemini-2.5-flash"},
    "minimax": {"url": "http://192.168.80.107:11438", "key": "xL5jUNR9A2lhN5HfLt1ulp9gE2CnBKf4",     "model": "MiniMax-M2.7"},
}


def stage_e_cross_vendor_review(text_en: str, draft_ar: str,
                                 term_hints: Dict[str, Any],
                                 reviewer: str = "codex") -> Dict[str, Any]:
    """Send source + draft to a second LLM proxy for cross-vendor review.
    Returns {available, verdict, corrections, raw_response}.
    Verdicts: 'pass' (faithful translation), 'minor_issues' (small fixes
    suggested), 'major_issues' (re-translation recommended), 'review_failed'.
    """
    if reviewer not in _REVIEW_PROXIES:
        return {"available": False, "reason": f"unknown reviewer: {reviewer}"}
    p = _REVIEW_PROXIES[reviewer]
    # Build the review prompt with the expected terminology
    term_lines = []
    for h in term_hints.get("asset_g_terminology_hits", [])[:10]:
        term_lines.append(f"  - {h['en']} → {h['ar']} (corpus-attested)")
    term_block = "\n".join(term_lines) if term_lines else "  (none provided)"
    system_prompt = (
        "You are an Arabic translation reviewer. Given an English source and an "
        "Arabic draft, return ONLY a JSON object with this shape: "
        '{"verdict":"pass|minor_issues|major_issues","corrections":[{"ar":"...","should_be":"...","reason":"..."}]}. '
        "Verdict 'pass' means the AR is faithful and uses the expected terminology. "
        "'minor_issues' means small word-choice fixes only. 'major_issues' means a "
        "mistranslation or missing content. corrections is a list of specific token "
        "substitutions; empty list if verdict is 'pass'. NO prose outside the JSON."
    )
    user_prompt = (
        f"# English source\n{text_en}\n\n"
        f"# Arabic draft\n{draft_ar}\n\n"
        f"# Expected terminology (from corpus)\n{term_block}\n\n"
        f"Review. Output JSON only."
    )
    body = json.dumps({
        "model": p["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=p["url"] + "/v1/chat/completions",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        return {"available": True, "verdict": "review_failed",
                "corrections": [], "error": str(e), "reviewer": reviewer}
    # Parse JSON out of the response (tolerate markdown fences)
    parsed = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    if not isinstance(parsed, dict):
        return {"available": True, "verdict": "review_failed",
                "corrections": [], "error": "could not parse JSON",
                "raw_response": content[:500], "reviewer": reviewer}
    return {
        "available": True,
        "reviewer": reviewer,
        "verdict": parsed.get("verdict", "review_failed"),
        "corrections": parsed.get("corrections", []),
        "raw_response": content[:1000],
    }


def apply_cross_vendor_corrections(draft_ar: str,
                                    corrections: List[Dict[str, str]]) -> Tuple[str, int]:
    """Apply the reviewer's specific token substitutions. Returns (new_draft, n_applied).
    Only applies substitutions where 'ar' appears exactly in draft_ar — refuses to
    invent corrections that don't have a clean substring match."""
    n_applied = 0
    for c in corrections:
        old = (c.get("ar") or "").strip()
        new = (c.get("should_be") or "").strip()
        if not old or not new or old == new:
            continue
        if old in draft_ar:
            draft_ar = draft_ar.replace(old, new)
            n_applied += 1
    return draft_ar, n_applied


def stage_c_llm_draft(text_en: str, term_hints: Dict[str, Any],
                      tm_hints: Dict[str, Any], domain: str,
                      proxy_name: Optional[str] = None) -> Dict[str, Any]:
    """Call the configured LLM endpoint. Returns the AR draft + metadata.

    v1.2.0: if proxy_name is one of {kimi, codex, gemini, minimax}, uses the
    LAN-local proxy fleet directly (no env vars needed). Otherwise falls back
    to LLM_API_URL/LLM_API_KEY/LLM_MODEL env vars (v1.0.x pattern).
    """
    if proxy_name and proxy_name in _REVIEW_PROXIES:
        p = _REVIEW_PROXIES[proxy_name]
        api_url = p["url"] + "/v1/chat/completions"
        api_key = p["key"]
        model = p["model"]
    else:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    if not api_url or not api_key:
        return {
            "draft_ar": "[LLM_API_URL or LLM_API_KEY not configured — set env vars to enable Stage C]",
            "input_en_preview": text_en[:200],
            "term_hints_count": term_hints.get("matched_count", 0),
            "tm_hits_count": len(tm_hints.get("tm_hits", [])),
            "domain": domain,
            "ok": False,
            "error": "missing LLM_API_URL or LLM_API_KEY",
        }

    system_prompt, user_prompt = _build_llm_prompt(text_en, term_hints, domain)

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {
            "draft_ar": "",
            "ok": False,
            "error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}",
            "domain": domain,
        }
    except (urllib.error.URLError, TimeoutError) as e:
        return {
            "draft_ar": "",
            "ok": False,
            "error": f"network: {e}",
            "domain": domain,
        }

    try:
        draft = payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        return {
            "draft_ar": "",
            "ok": False,
            "error": f"malformed LLM response: {e}; raw[0:300]: {str(payload)[:300]}",
            "domain": domain,
        }

    return {
        "draft_ar": draft,
        "input_en_preview": text_en[:200],
        "term_hints_count": term_hints.get("matched_count", 0),
        "tm_hits_count": len(tm_hints.get("tm_hits", [])),
        "domain": domain,
        "model": model,
        "ok": True,
    }


# ---------------------------------------------------------------------------
# Stage D — Validator (v0.2 — calque-rate metric implemented)
# ---------------------------------------------------------------------------

def _arabic_word_boundary_search(needle: str, haystack: str) -> bool:
    """v0.2.1: Word-boundary-aware substring search for Arabic text.

    Plain `needle in haystack` matched 'بيان' inside 'البيانات' (false
    positive on a longer Arabic word containing the needle). Fix follows
    the humanizer v2.4.5 pattern: require the matched span to NOT be
    followed by an Arabic letter (lookahead negation).

    Note: we don't restrict the LEADING boundary, because Arabic proclitics
    (بـ, لـ, كـ, ال) attach to the word; 'البيانات' contains 'البيان' as
    a real partial match (the definite article + base word), but 'بيان'
    standing alone inside 'البيانات' is what we want to reject. The
    trailing-letter check accomplishes that: 'البيانات' is 'البيان' + 'ات'
    so a 'بيان' lookup would find a match but fail the trailing-non-letter
    test.
    """
    if not needle or not haystack:
        return False
    # Arabic letter block: U+0621-U+064A (plus U+0670 dagger alif).
    arabic_letter_re = r"[ء-يٰ]"
    pat = re.escape(needle) + r"(?!" + arabic_letter_re + r")"
    return re.search(pat, haystack) is not None


def stage_d_validate(draft_ar: str, source_en: str) -> Dict[str, Any]:
    """Score the AR draft on:
      - calque_rate: how many ai_default_calque entries appear (word-boundary safe)
      - term_fidelity: how many natural_arabic forms appear (word-boundary safe)
      - n_gram_naturalness: STUB (deferred to v0.3+ when corpus_stats.py wired in)

    v0.2.1: switched from naive `in` substring match to word-boundary
    regex to eliminate false positives like `بيان` matching inside
    `البيانات`. Same fix pattern as humanizer v2.4.5.

    v0.2.2: Asset C lexical-cleanup applied BEFORE scoring. If the LLM
    produced AI-tell phrases (e.g., 'من المهم ملاحظة') and Asset C can
    fix them deterministically, we apply the fix and score the cleaned
    draft. The 'cleaned_draft_ar' and 'lexical_cleanup' fields in the
    returned dict report what happened. If Asset C isn't available
    (toolkit pre-v0.7 or missing entirely), behavior matches v0.2.1.
    """
    cleaned_draft, cleanup_diag = apply_lexical_cleanup(draft_ar)
    # If anything was applied, validate the CLEANED text; otherwise validate
    # the original draft (semantically identical).
    text_to_score = cleaned_draft

    entries = _load_calque_entries()
    if not entries:
        return {
            "calque_hits": [],
            "natural_hits": [],
            "calque_count": 0,
            "natural_count": 0,
            "calque_rate_per_1k_tokens": None,
            "term_fidelity": None,
            "n_gram_naturalness": None,
            "verdict": "skipped (toolkit not found)",
            "cleaned_draft_ar": cleaned_draft,
            "lexical_cleanup": cleanup_diag,
        }

    calque_hits: List[str] = []
    natural_hits: List[str] = []
    for e in entries:
        calque = e.get("ai_default_calque", "").strip()
        natural = e.get("natural_arabic", "").strip()
        if calque and _arabic_word_boundary_search(calque, text_to_score):
            calque_hits.append(calque)
        if natural and _arabic_word_boundary_search(natural, text_to_score):
            natural_hits.append(natural)

    # Crude token count (whitespace-separated)
    tokens = len(re.findall(r"\S+", text_to_score))
    calque_rate = (len(calque_hits) * 1000.0 / tokens) if tokens > 0 else 0.0
    term_fidelity = (
        len(natural_hits) / (len(natural_hits) + len(calque_hits))
        if (len(natural_hits) + len(calque_hits)) > 0
        else 1.0
    )

    # Verdict — pass if calque rate is low AND term fidelity is high
    if calque_rate <= 1.0 and term_fidelity >= 0.9:
        verdict = "pass"
    elif calque_rate <= 3.0 and term_fidelity >= 0.7:
        verdict = "warning"
    else:
        verdict = "fail"

    return {
        "calque_hits": calque_hits[:20],  # cap for readability
        "natural_hits": natural_hits[:20],
        "calque_count": len(calque_hits),
        "natural_count": len(natural_hits),
        "calque_rate_per_1k_tokens": round(calque_rate, 2),
        "term_fidelity": round(term_fidelity, 3),
        "n_gram_naturalness": None,  # deferred to v0.3
        "verdict": verdict,
        "thresholds": {
            "pass": "calque_rate <= 1.0 AND term_fidelity >= 0.9",
            "warning": "calque_rate <= 3.0 AND term_fidelity >= 0.7",
        },
        "cleaned_draft_ar": cleaned_draft,
        "lexical_cleanup": cleanup_diag,
    }


# ---------------------------------------------------------------------------
# Stage B — Translation Memory (still stubbed pending v0.3 alignment work)
# ---------------------------------------------------------------------------

def stage_b_tm_lookup(text_en: str, domain: str) -> Dict[str, Any]:
    """v1.0.0: DEFINITIVELY DROPPED. The SPA corpus diagnostic (v0.1.1) confirmed
    Y:\\Linguistics\\NewsDataForTranslation has 0 paired articles. Title-similarity
    alignment (Option A) was considered for v0.3+ but never shipped because:
      (1) The corpus state hasn't changed (download is still partial).
      (2) Stage A + Asset G now provide rich terminology hints (422 tech + 50
          news pairs cross-vendor-validated), making TM redundant for common
          terms.
      (3) Stage D (LLM-cleaned validation with calque dictionary + corpus
          confirmation) catches what TM would have caught.
    The 3-stage pipeline (A → C → D) is the v1.0.0 contract. Stage B remains
    in the return shape for backward compatibility with v0.2-v0.3 consumers
    but is a documented no-op.
    """
    return {
        "tm_hits": [],
        "status": "dropped_in_v1.0.0",
        "reason": "Corpus has 0 paired articles; Stage A + Asset G provide better terminology hints; Stage D catches what TM would catch.",
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def translate(text_en: str, domain: str, strict: bool = False, max_regen: int = 3,
              review_with: Optional[str] = None,
              auto_apply_corrections: bool = True,
              llm_proxy: Optional[str] = None) -> Dict[str, Any]:
    """Full pipeline. v0.2: A + C real, B stubbed, D real.
    On verdict=='fail' AND strict=True, returns with strict_failure=True.
    """
    stage_a = stage_a_terminology(text_en, domain)
    stage_b = stage_b_tm_lookup(text_en, domain)

    stage_c = stage_c_llm_draft(text_en, stage_a, stage_b, domain, proxy_name=llm_proxy)
    stage_d = stage_d_validate(stage_c.get("draft_ar", ""), text_en)

    # Simple regen loop. On 'fail' verdict, retry up to max_regen times.
    regen_count = 0
    while stage_d.get("verdict") == "fail" and regen_count < max_regen and stage_c.get("ok"):
        regen_count += 1
        sys.stderr.write(f"  Validator returned 'fail'; regen attempt {regen_count}/{max_regen}\n")
        stage_c = stage_c_llm_draft(text_en, stage_a, stage_b, domain, proxy_name=llm_proxy)
        stage_d = stage_d_validate(stage_c.get("draft_ar", ""), text_en)

    strict_failure = strict and stage_d.get("verdict") == "fail"

    # v0.2.2: prefer the lexically-cleaned draft if Asset C was available
    # (the cleaned draft IS what Stage D scored). If Asset C wasn't found,
    # cleaned_draft_ar equals the raw draft (apply_lexical_cleanup is a no-op
    # when the asset is missing).
    output_ar = stage_d.get("cleaned_draft_ar") or stage_c.get("draft_ar", "")

    # v1.1.0: optional Stage E cross-vendor review
    stage_e = None
    if review_with:
        stage_e = stage_e_cross_vendor_review(text_en, output_ar, stage_a, reviewer=review_with)
        if auto_apply_corrections and stage_e.get("corrections"):
            output_ar, n_applied = apply_cross_vendor_corrections(output_ar, stage_e["corrections"])
            stage_e["corrections_applied"] = n_applied

    return {
        "translator_version": "1.2.0",
        "domain": domain,
        "stages": {
            "A_terminology": stage_a,
            "B_tm_lookup": stage_b,
            "C_llm_draft": stage_c,
            "D_validator": stage_d,
            "E_cross_vendor_review": stage_e,
        },
        "regen_count": regen_count,
        "output_ar": output_ar,
        "raw_llm_draft_ar": stage_c.get("draft_ar", ""),
        "strict_mode": strict,
        "strict_failure": strict_failure,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="arabic-corpus-translator v0.2 — 3-stage pipeline")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", help="EN text file to translate")
    src.add_argument("--text", "-t", help="EN text inline")
    p.add_argument("--domain", "-d", default="news",
                   help="Domain hint. Default: news.")
    p.add_argument("--output", "-o", help="Write AR output to this file")
    p.add_argument("--analyze", action="store_true",
                   help="Stage A only — list term hints without calling LLM")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero if Stage D validator returns 'fail'")
    p.add_argument("--max-regen", type=int, default=3, help="Max regen attempts on validator fail")
    p.add_argument("--llm-proxy", choices=["kimi", "codex", "gemini", "minimax"],
                   help="Stage C: use a LAN-local proxy (no env vars needed). If unset, uses LLM_API_URL/LLM_API_KEY env vars.")
    p.add_argument("--review-with", choices=["kimi", "codex", "gemini", "minimax"],
                   help="Stage E: send the translation through a second LLM proxy for cross-vendor review. "
                        "If correction suggestions come back, auto-applies them (unless --no-auto-correct).")
    p.add_argument("--no-auto-correct", action="store_true",
                   help="Disable auto-application of Stage E corrections (report only).")
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

    result = translate(text, args.domain, strict=args.strict, max_regen=args.max_regen,
                       review_with=args.review_with,
                       auto_apply_corrections=not args.no_auto_correct,
                       llm_proxy=args.llm_proxy)
    if args.output:
        Path(args.output).write_text(result["output_ar"], encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["output_ar"])

    return 1 if result.get("strict_failure") else 0


if __name__ == "__main__":
    sys.exit(main())
