---
name: arabic-corpus-translator
description: "Corpus-grounded English↔Arabic translation skill. Uses arabic-corpus-toolkit as its terminology base (340-entry calque dictionary with topic guards, regional + political sensitivity annotations, multi-LLM-validated). Four-stage pipeline: (A) terminology lookup from the toolkit, (B) Translation Memory fuzzy-match against the SPA bilingual corpus (38,886 article pairs in Y:\\Linguistics\\NewsDataForTranslation), (C) LLM draft with terminology + TM hints injected, (D) validator that scores output on calque-rate / term-fidelity / n-gram naturalness. v0.1 ships the architecture scaffold + CLI shape; Stages B+D are stubs pending v0.2 mining work. RTL/Arabic-first. Triggers on 'translate to Arabic', 'translate from Arabic', 'EN→AR translation', 'ترجمة', 'تعريب', 'translate this news article', 'localize to MSA'. Do NOT use for: dialectal translations (MSA-only), creative literary translation (use a literary translator), code documentation (preserve technical English), already-Arabic text (no-op or use arabic-ai-text-humanizer instead)."
---

# arabic-corpus-translator — Corpus-Grounded EN↔AR Translation

**Status:** **v1.6.0 — STABLE.** Third-audit consensus closure (Codex + Gemini #1 action: "complete asset_registry migration by removing the three legacy schema_major == '1' loader fallbacks" + "adopt arabic_normalize in Stage D"). v1.6.0 ships both: (a) `_stage_d_normalize()` routes Stage D text-to-score through toolkit `arabic_normalize.normalize(level="light")` with raw-text fallback, eliminating bespoke tokenization (G1 adoption); (b) the 3 loader sites (`_load_terminology_candidates` for F.{domain}, `_load_domain_terminology` for G.{domain}, `_load_lexical_tables_from_toolkit` for C) now use `_check_asset_compat(asset_id, observed)` exclusively — legacy inline `schema_major != "1"` checks removed (G2 full adoption). Each loader passes the correct registry asset_id (F.technology, F.news, G.technology, G.news, C) per call. Verified: `الذكاءِ الاصطناعيّ → الذكاء الاصطناعي` via shared contract; all 3 asset loaders succeed via registry; 0 legacy `schema_major != "1"` checks remain in runtime code (only 1 comment-header reference left). **v1.5.1 — STABLE.** Sonnet re-audit (77/100, +15 from baseline) flagged this status line as stuck at v1.3.1 despite code reaching v1.5.0; v1.5.1 corrects the drift. **v1.5.0** wired Stage A into the toolkit's `influence_telemetry` contract (Gap G3 adoption) — every Asset G `term_hint_injected` is recorded with `{asset_id, asset_version, trigger, evidence, stage}` and surfaced in output JSON's `influence_trace` field. **v1.4.0** adopted toolkit's `asset_registry` (Gap G2): `_check_asset_compat()` routes through `registry.is_compatible()` with legacy `schema_major == "1"` as fallback when toolkit pre-v1.6.0 — half-migration acknowledged in re-audit; full removal queued. **v1.3.1** added explicit stderr warning when toolkit not found. **v1.3.0** added Stage F quality gate via humanizer (`--quality-gate` flag uses `score_text`; `--deep-quality` uses `score_text_deep` with LLM-backed 4-dim cognitive rubric). **v1.2.0** added native `--llm-proxy {kimi,codex,gemini,minimax}` flag for Stage C (LAN proxies, no env vars). **v1.1.0** added Stage E cross-vendor translation review (catches single-LLM hallucinations — auto-correction of safe substring patches). **v1.0.1** added multi-domain Asset G support (`--domain news` uses domain-terminology-news.json). **v1.0.0 — STABLE.** 3-stage pipeline (A → C → D); Stage B definitively dropped (corpus reality + Asset G makes TM redundant). Stage A reads three toolkit assets (calque-dictionary A + terminology-candidates F + paired-terminology G) producing complementary signals: calque corrections, corpus-confirmation flags, direct EN-AR pair injection. Stage D applies Asset C lexical-cleanup before scoring. 16/16 eval-suite tests pass. Pinned to `arabic-corpus-toolkit >= v1.0.0` (per-asset SemVer enforced; refuses MAJOR schema bumps in any asset). v0.3.1 — **Asset G (paired EN↔AR terminology) wired into Stage A as direct term-pair injection.** Builds on v0.3.0's Asset F verification signal. Now Stage A returns THREE complementary signals: (1) Asset A calque-dictionary recommendations with `corpus_confirmed` flag, (2) Asset F-derived corpus confirmation for each calque hit, (3) Asset G direct EN→AR pair hits via whole-word scan of input text. Measured impact on tech-sentence test: 1 Asset A hit + 8 Asset G hits = 9 terminology hints in the LLM prompt where v0.3.0 had only 1. Asset G covers terms the calque dictionary doesn't (artificial intelligence, 5G, instant messaging, IoT, TikTok, MacBook) — they're not AI errors to fix, they're standard terminology that simply wasn't in Asset A's error catalog. v0.3.0 — **Asset F (terminology candidates) wired into Stage A as a corpus-confirmation signal.** When the toolkit's `terminology-candidates-<domain>.json` is available (toolkit v0.8+), each Stage A term hint gets two new fields: `corpus_confirmed: bool` (whether the dictionary's suggested `natural_ar` form appears in the corpus-mined candidates) and `corpus_freq: int` (the AITNews/Elaph frequency). Verified end-to-end: `الذكاء الاصطناعي` confirmed at freq 8,146; `الحوسبة السحابية` at freq 1,859; Saudi-specific terms like `الشخصنة` correctly flagged as dictionary-only (not in pan-Gulf tech corpus). The LLM prompt now distinguishes "dictionary + corpus-attested" (highest authority) from "dictionary-only" (legacy fallback). v0.2.3 — `ARABIC_CORPUS_TOOLKIT_DISABLE=1` kill-switch matching humanizer v2.7.2 semantics. (strict literal-`1` match). Set this env var to skip toolkit loading entirely: Stage A returns empty term hints, Stage D's lexical cleanup is a no-op (`asset_available=0`), Stage C runs unaffected. Useful for isolating the toolkit's contribution when debugging output differences across the four-sibling family. v0.2.2 — **3-stage pipeline + Asset C lexical-cleanup in Stage D.** v0.2.2 wires the toolkit's Asset C (lexical-tables, shipped in toolkit v0.7+) into Stage D: a conservative deterministic subset (`ai_phrases` first-non-empty alternative + `intensifier_destack` regex patterns) cleans the LLM draft *before* scoring. Probabilistic substitutions (connectors, quote-verb rotation, repetitive-starter detection, fillers, structural openers) are intentionally skipped — the translator's contract is reproducibility, not the humanizer's variance-for-humanness. Cleaned draft becomes user-facing `output_ar`; raw LLM draft exposed at `raw_llm_draft_ar` for quality monitoring. v0.2.1 — word-boundary regex fix for Stage D false positives (`بيان` inside `البيانات`). v0.2 — **working 3-stage pipeline (Option B from the corpus reality check).**

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
