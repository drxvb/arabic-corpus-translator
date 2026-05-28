# 04 — Corpus Reality Check (v0.1.1)

This file documents an honest correction. It's permanent. Do not delete.

## The original claim (v0.1)

`SKILL.md` v0.1 and the `arabic-corpus-translator/README.md` v0.1 both claimed:

> "Stage B: mine `Y:\Linguistics\NewsDataForTranslation\_corpus\parallel\` (38,886 UUID-aligned pairs already exists — pre-mining done) into a SQLite FTS5 index for fuzzy lookup"

That claim originated in Agent B's translation-engine design recommendation in the v2.6.0 multi-agent review of `arabic-ai-text-humanizer`. Agent B inferred the alignment was pre-built from:

1. The user's reference to `Y:\Linguistics\NewsDataForTranslation` as a "TM-ready resource"
2. The presence of `_corpus/parallel/` subdirectory (containing `spa_parallel.jsonl`, `spa_parallel_paragraphs.jsonl`, `spa_parallel.tsv`)
3. The `translations: [{uuid, locale}]` cross-reference field in sampled `en.json` articles
4. The `_corpus/README.md`'s stated metric of "~20,000+ pairs (estimated)"

I (the assistant) propagated this claim into v0.1 of the translator skill **without verifying it.** That was wrong.

## What the user discovered (and the diagnostic confirmed)

After v0.1 shipped, the user inspected `_corpus/parallel/` and reported it was empty. A full-corpus diagnostic (`scripts/diagnose_corpus.py`) scanned all 77,756 article directories and produced this ground truth:

```
=== File layout ===
en_only directories:  38,897
ar_only directories:  38,859
both (paired):              0
neither:                    0

=== _corpus/parallel/ index files ===
spa_parallel.jsonl:               0 KB
spa_parallel_paragraphs.jsonl:    0 KB
spa_parallel.tsv:                 0.1 KB

=== Cross-reference resolution (200-article random samples) ===
EN-side: 0 resolved / 162 unresolved / 38 empty translations[]
AR-side: 11 resolved / 56 unresolved / 133 empty translations[]
Estimated EN→AR alignable pairs: 0 (0.0% resolution rate)
```

## What this means architecturally

The corpus IS real and valuable, but it is **two disjoint monolingual collections**:

- 38,897 EN articles (each in its own `N<uuid>/en.json`)
- 38,859 AR articles (each in its own `N<uuid>/ar.json`)
- ZERO directories contain both languages
- The `translations[]` cross-reference field in en.json points to UUIDs that **don't exist in the dataset** (the AR sibling of `N2097580` should be at `N2097479` — that directory is missing)
- AR articles often have `translations: []` (no claimed EN counterpart at all)

Agent B's design assumed **pre-built alignment**. That doesn't exist.

## Architectural pivot for v0.2

The original 4-stage pipeline (Terminology → TM → LLM Draft → Validator) needs revision. Three options, in order of recommendation:

### Option A — Title-similarity alignment (recommended)

Build EN↔AR pairs by fuzzy-matching article titles across the two monolingual collections. Pipeline:

1. Extract `title` + `published_at` + `category` from each `en.json` and `ar.json`
2. Embed each title with a multilingual model (LaBSE or multilingual-E5)
3. For each EN title, find top-K nearest cross-language matches within a ±3-day publication window
4. Filter to high-similarity matches (cosine ≥ 0.85)
5. Output `spa_aligned.jsonl` — our own parallel index

Estimated yield: 5-15% pair rate (~2K-6K usable pairs). Lower than Agent B assumed, but mineable and honest.

Cost: requires loading a multilingual embedding model — adds a dependency. Could be done as a one-time offline mining run.

### Option B — Drop Stage B, ship 3-stage translator

Skip TM lookup entirely. v0.2 ships as Terminology + LLM Draft + Validator. The monolingual corpora feed Stage D (n-gram naturalness scoring) instead of Stage B.

Simpler architecture, lower yield ceiling, but **honest** about what the corpus actually delivers.

### Option C — Monolingual-only enrichment

Use the 38K+ EN articles and 38K+ AR articles purely for monolingual reference: per-language n-gram language models, term frequencies, register-classification training data. No alignment attempted; the translator becomes Term-dictionary + LLM-draft + Sophisticated-validator.

## What v0.1.1 ships (this release)

- **Corrected SKILL.md** — accurate corpus characterization, three architectural pivot options
- **Corrected README.md** — explicit warning about the v0.1 claim
- **`scripts/diagnose_corpus.py`** — the diagnostic tool that produced the ground truth; runnable for re-verification
- **`corpus/corpus_diagnostic.json`** — saved diagnostic output as evidence
- **This file (`references/04-corpus-reality-check.md`)** — permanent record

## Lessons internalized

1. **Verify load-bearing claims before they ship.** Agent B's design was reasonable given the data they had. I should have run the diagnostic before adopting the claim into the skill.
2. **Multi-agent design recommendations need ground-truth checks**, not just internal consistency checks. The v2.6.0 review caught dictionary errors via native review; the v0.1 corpus assumption needed a directory walk.
3. **"Pre-built alignment" was a category error.** A `parallel/` subdirectory with zero-byte files is not pre-built alignment — it's a scaffold. I should have opened those files.
4. **Honesty cost is small; silent-bug cost is large.** v0.1.1 fixes the false claim within ~24 hours of v0.1 shipping. That's better than a future user discovering the gap and losing trust.

## Provenance

Diagnostic run: 2026-05-28. Scan duration: ~3 minutes. Output: `corpus/corpus_diagnostic.json`. Diagnostic tool source: `scripts/diagnose_corpus.py`. Reviewer: the user (`basil.baziz@gmail.com`) who explicitly checked the parallel directory and reported it empty.
