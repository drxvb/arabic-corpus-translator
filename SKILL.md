---
name: arabic-corpus-translator
description: "Corpus-grounded English↔Arabic translation skill. Uses arabic-corpus-toolkit as its terminology base (340-entry calque dictionary with topic guards, regional + political sensitivity annotations, multi-LLM-validated). Four-stage pipeline: (A) terminology lookup from the toolkit, (B) Translation Memory fuzzy-match against the SPA bilingual corpus (38,886 article pairs in Y:\\Linguistics\\NewsDataForTranslation), (C) LLM draft with terminology + TM hints injected, (D) validator that scores output on calque-rate / term-fidelity / n-gram naturalness. v0.1 ships the architecture scaffold + CLI shape; Stages B+D are stubs pending v0.2 mining work. RTL/Arabic-first. Triggers on 'translate to Arabic', 'translate from Arabic', 'EN→AR translation', 'ترجمة', 'تعريب', 'translate this news article', 'localize to MSA'. Do NOT use for: dialectal translations (MSA-only), creative literary translation (use a literary translator), code documentation (preserve technical English), already-Arabic text (no-op or use arabic-ai-text-humanizer instead)."
---

# arabic-corpus-translator — Corpus-Grounded EN↔AR Translation

**Status:** v0.2 — **working 3-stage pipeline (Option B from the corpus reality check).**

`scripts/translate.py` ships a real implementation of:
- **Stage A** (Terminology lookup) — reads toolkit's 340-entry calque dictionary with topic-guard + domain filtering
- **Stage C** (LLM Draft) — calls any OpenAI-compatible endpoint via `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL` env vars; builds a structured prompt that injects the Stage-A term table + political-sensitivity warnings; stdlib `urllib.request` only
- **Stage D** (Validator) — scores the AR draft on calque-rate-per-1K-tokens + term-fidelity; verdict `pass` / `warning` / `fail`; up to 3 regen attempts on `fail` (configurable)
- **Stage B** (TM lookup) — remains stubbed; cannot be built from the current SPA corpus (per the v0.1.1 diagnostic). Deferred to v0.3+ via title-similarity alignment (Option A) once viable.

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

The architecture is a 4-stage pipeline:

```
INPUT (EN text)
    │
    ▼
┌────────────────────────────────────────┐
│ Stage A — TERMINOLOGY                  │ ← arabic-corpus-toolkit (340-entry dict)
│ Look up known calque corrections       │
│ + topic-guard + exclusion-pattern gates│
└────────────────┬───────────────────────┘
                 │ uncovered spans
                 ▼
┌────────────────────────────────────────┐
│ Stage B — TRANSLATION MEMORY (v0.2+)   │ ← SPA bilingual corpus
│ Fuzzy-match against 38,886 EN/AR pairs │   (UUID-aligned)
│ Threshold: ≥0.85 sim                   │
└────────────────┬───────────────────────┘
                 │ no TM hit
                 ▼
┌────────────────────────────────────────┐
│ Stage C — LLM DRAFT                    │ ← provider-agnostic
│ Prompt includes term hits + TM         │   (OpenAI-compatible)
│ near-misses + style refs               │
└────────────────┬───────────────────────┘
                 ▼
┌────────────────────────────────────────┐
│ Stage D — VALIDATOR (v0.2+)            │ ← arabic-corpus-toolkit
│ - Calque-rate (uses humanizer's        │   (calque-rate detector)
│   calque dictionary as detector)       │
│ - Term-fidelity (% of in-domain terms  │
│   matching natural_arabic)             │
│ - N-gram naturalness (corpus LM)       │
│ Regen up to 3 times if validator fails │
└────────────────────────────────────────┘
                 ▼
OUTPUT (AR text) + provenance per span
```

## v0.1 scope (this release)

- Skill spec (this file) declaring the 4-stage architecture
- CLI shape in `scripts/translate.py` — argparse + mode flags wired, but Stages B and D are TODO stubs that return placeholder output
- `references/02-architecture.md` — full per-stage design notes
- `references/03-eval-strategy.md` — how the "better than corpus baseline" claim becomes measurable (calque-rate reduction ≥60% vs GPT-4o-class baseline; term-fidelity ≥90%; n-gram perplexity within 1 stddev of human-written news)

## v0.2 plan (REVISED post-diagnostic)

Three options for Stage B given the corpus reality:

### Option A — Title-similarity alignment (recommended)

Build EN↔AR pairs by fuzzy-matching article titles across the two monolingual collections. Estimated yield: **5-15% pair rate** (~2K-6K usable pairs). Lower than Agent B assumed, but still meaningful seed data.

Pipeline: extract title+date+category from each en.json and ar.json → embed with a multilingual model (LaBSE / multilingual-E5) → top-K nearest cross-language match within ±3-day publication window → confidence-filtered.

### Option B — Drop Stage B (simpler, honest)

Ship the v0.2 translator as **3-stage** (Terminology + LLM Draft + Validator). Skip TM entirely. Simpler, still useful. The monolingual corpora feed Stage D (n-gram naturalness) instead of Stage B.

### Option C — Monolingual-only mining

Build per-language n-gram language models from the 38K+ EN articles and 38K+ AR articles. Use them in Stage D for fluency scoring. No Stage B; Stage D becomes more sophisticated.

### Other v0.2 work (unchanged from v0.1 plan)

- Stage D: implement calque-rate + term-fidelity + n-gram naturalness scoring
- Adversarial eval set: curate 200 sentences where AI is known to fail
- LLM backend integration: provider-agnostic via `LLM_API_URL`/`LLM_API_KEY`/`LLM_MODEL`

## Dependencies

- **`arabic-corpus-toolkit`** (v0.4+) — calque dictionary, register policies, corpus statistics. Read via `sys.path` discovery or `ARABIC_CORPUS_TOOLKIT_ROOT` env var. Same resolution pattern as `arabic-ai-text-humanizer` v2.7.0.
- **`arabic-ai-text-humanizer`** (optional, for Stage D) — calque-rate detector reused as a quality scorer. NOT required at v0.1 because Stage D is stubbed; required by v0.2.

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
