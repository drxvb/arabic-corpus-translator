---
name: arabic-corpus-translator
description: "Corpus-grounded English↔Arabic translation skill. v1.9.0 stable. Hard dependency on arabic-corpus-toolkit ≥ v1.13.0 (Stage C adopts the shared `safe_llm_call` resilience contract — retries + circuit breaker + structured failure envelope; falls back to legacy inline urllib on pre-v1.13.0 toolkit; the foundational G1-G4 contracts need ≥ v1.5.0). 5-stage pipeline: (A) terminology lookup — toolkit's 340-entry calque dictionary + Asset F corpus confirmation + Asset G direct EN↔AR pair injection (covers 13 domain assets including SPA-2024-mined business/legal/politics tiered by 3-vendor consensus); (C) LLM draft via configurable proxy (kimi/codex/gemini/minimax/any-OpenAI-compatible); (D) validator with calque-rate + term-fidelity + n-gram naturalness, G1 normalize routed through toolkit, regen up to max_regen on verdict=fail; (E) cross-vendor review with safe-substring auto-correction emitting cross_vendor_correction telemetry; (F) humanizer quality gate (`--quality-gate` heuristic / `--deep-quality` 4-dim cognitive rubric). Stage B (Translation Memory fuzzy-match) was definitively dropped after the v0.1.1 corpus-reality check found the assumed bilingual alignment didn't exist in the source corpus; Asset G's paired terminology + Asset F's mined candidates render TM redundant. Per-stage InfluenceTrace emits causal G3 records. v1.8.0 added the `min_consensus` filter API (restrict Asset G hints to majority/unanimous-validated terminology); v1.9.0 routed Stage C through the toolkit's `safe_llm_call` for retry + per-vendor circuit-breaker resilience, returning structured `error_class`/`attempts`/`circuit_open` so callers distinguish transient from terminal LLM failures. RTL/Arabic-first. Triggers on 'translate to Arabic', 'translate from Arabic', 'EN→AR translation', 'ترجمة', 'تعريب', 'translate this news article', 'localize to MSA'. Do NOT use for: dialectal translations (MSA-only), creative literary translation (use a literary translator), code documentation (preserve technical English), already-Arabic text (no-op or use arabic-ai-text-humanizer instead)."
---

# arabic-corpus-translator — Corpus-Grounded EN↔AR Translation

**Status:** **v1.9.0 — STABLE.** Corpus-grounded EN↔AR translation; 5-stage pipeline (A terminology lookup → C LLM draft → D validator → E cross-vendor review → F humanizer gate). Stage C adopts toolkit v1.13.0 `safe_llm_call` (retries + per-vendor circuit breaker + structured failure envelope: `error_class`/`attempts`/`circuit_open`); falls back to legacy inline urllib on pre-v1.13.0 toolkit. `min_consensus` filters Asset G terminology by 3-vendor consensus tier. Per-stage G3 `InfluenceTrace`. Stage B (Translation Memory) was **definitively dropped** — the v0.1.1 corpus-reality check found 0 paired directories in 77,756; Asset G + Asset F make TM redundant. **Full version history → [`CHANGELOG.md`](CHANGELOG.md).**

`scripts/translate.py` ships a real implementation of:
- **Stage A** (Terminology lookup) — reads toolkit's 340-entry calque dictionary with topic-guard + domain filtering
- **Stage C** (LLM Draft) — calls any OpenAI-compatible endpoint via `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL` env vars; builds a structured prompt that injects the Stage-A term table + political-sensitivity warnings; stdlib `urllib.request` only
- **Stage D** (Validator) — scores the AR draft on calque-rate-per-1K-tokens + term-fidelity; verdict `pass` / `warning` / `fail`; up to 3 regen attempts on `fail` (configurable)
- **Stage B** (TM lookup) — **dropped** (not stubbed-pending). The v0.1.1 corpus diagnostic below found 0 paired directories; Asset G's paired terminology + Asset F's mined candidates make TM redundant. The 4-stage diagram further down is retained as historical design context — the shipped pipeline is A → C → D → E → F.

Discovered post-v0.1 ship: the corpus state assumed by Agent B's design **does not match reality.** Ground truth from `scripts/diagnose_corpus.py` (full scan of all 77,756 article directories):

| Layout | Actual count |
|---|---|
| EN-only directories | **38,897** |
| AR-only directories | **38,859** |
| Paired (both en.json + ar.json) | **0** |
| Resolvable EN→AR cross-references | ~0% (0/200 in random sample) |
| Resolvable AR→EN cross-references | ~5.5% (11/200 in random sample) |
| `_corpus/parallel/spa_parallel.jsonl` (pre-built index) | **0 KB — empty** |

**What this means architecturally:**
- The `_corpus/parallel/` pre-built alignment files are empty placeholders, not populated data
- The `translations: [{uuid, locale}]` cross-reference field in en.json points to UUIDs that aren't in the dataset
- The corpus is effectively **two disjoint monolingual collections** with broken cross-references
- Stage B (TM lookup against 38,886 pairs) **cannot be built from this corpus as-is**

The 38,897 EN + 38,859 AR articles ARE valuable as **monolingual reference data** (for Stage D n-gram naturalness scoring + register learning + terminology mining), but not for direct alignment.

## Why this skill exists

Per the v2.6.0 multi-agent review of `arabic-ai-text-humanizer` (Agent B: translation engineering architect), the user's frustration that "AI always gives wrong translation for these" has a tractable engineering answer: **ground translation in a real Arabic corpus, not in the LLM's training data alone.**

The shipped pipeline is **5-stage: A (terminology) → C (LLM draft) → D (validator) → E (cross-vendor review) → F (humanizer gate)**. Stage B (Translation Memory) was dropped after the v0.1.1 corpus-reality check (the diagnostic table above shows 0 paired directories); Asset G's paired terminology + Asset F's mined candidates make TM redundant.

## Dependencies

- **`arabic-corpus-toolkit`** (≥ v1.13.0) — calque dictionary, register policies, corpus stats, `safe_llm_call` resilience. Resolved via `sys.path` discovery or `ARABIC_CORPUS_TOOLKIT_ROOT`.
- **`arabic-ai-text-humanizer`** (≥ v2.17.0, Stage F) — humanness quality gate.

## Scope discipline (the Humanizer-≠-Localizer descendant)

This skill is a **Translator**, NOT:

- A **Humanizer** — that's `arabic-ai-text-humanizer`. Use it AFTER translation if the output reads as AI-translated.
- A **Localizer** — BCP47 / ICU / SSML / locale plurals are out of scope (same boundary the humanizer's SKILL.md draws).
- An **Authoring Suite** — generating new content from a brief is a different category. The translator translates *existing* English to Arabic, not "write me an article."

The Humanizer-≠-Localizer principle from the v2.0 humanizer release applies recursively: each new sibling skill has a similar boundary it must defend.

## Operating modes

```bash
# Direct translation (v0.1: Stage A + Stage C only; Stages B + D are stubs)
python scripts/translate.py --input article-en.md --domain news --output article-ar.md

# Analyze only — find calque corrections that would apply, don't translate
python scripts/translate.py --analyze --input article-en.md --domain news

# Strict mode (planned v0.2) — refuse to ship if Stage D validator fails
python scripts/translate.py --strict --input article-en.md --domain news
```

## Provenance

The 4-stage architecture is directly from Agent B's design recommendation in the v2.6.0 multi-agent review of `arabic-ai-text-humanizer`. See `M:\Main\AI\Corpus\humanizer-v2.6-multi-agent-synthesis.md` for the original design doc.
