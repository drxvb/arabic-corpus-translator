# arabic-corpus-translator

> Corpus-grounded EN↔AR translation skill. Uses `arabic-corpus-toolkit` as its terminology base. Four-stage pipeline: terminology → Translation Memory → LLM draft → quality validator. RTL/Arabic-first.

**Status:** v0.1.1 — honest corpus-state correction.

**Important:** v0.1 claimed the corpus had "38,886 UUID-aligned EN/AR pairs ready." A post-ship diagnostic (`scripts/diagnose_corpus.py`, full scan of all 77,756 article dirs) found that's **NOT the case**:

- **0 paired dirs** (no en.json + ar.json co-located)
- **38,897 EN-only + 38,859 AR-only** (disjoint monolingual collections)
- **~0% cross-reference resolution** on EN-side (0/200 sampled)
- **~5.5%** on AR-side (11/200)
- `_corpus/parallel/*.jsonl` files are **0 KB** (placeholders, not populated)

The corpus is real and valuable as **monolingual reference data**, but the EN↔AR alignment Agent B's design assumed doesn't exist in the source. v0.2 will pivot to title-similarity alignment OR drop Stage B and ship as a 3-stage pipeline. See `references/04-corpus-reality-check.md` and `SKILL.md` for the revised plan.

## Why

The v2.6.0 multi-agent review of `arabic-ai-text-humanizer` identified an architectural gap: the user's frustration that "AI always gives wrong translation for these" has a tractable engineering answer — **ground translation in a real Arabic corpus, not in the LLM's training data alone.**

This skill operationalizes that. The 4-stage pipeline:

1. **Terminology** — look up known calque corrections from `arabic-corpus-toolkit/corpus/calque-dictionary.json` (340 entries with topic-guard + regional/political sensitivity annotations)
2. **Translation Memory** — fuzzy-match against the SPA bilingual corpus (38,886 UUID-aligned EN/AR article pairs)
3. **LLM Draft** — prompt the LLM with terminology + TM hints injected; provider-agnostic
4. **Validator** — score output on calque-rate / term-fidelity / n-gram naturalness; regen up to 3× if validator fails

## Family map

```
                              ┌─────────────────────────────┐
                              │  arabic-corpus-toolkit       │
                              │  (v0.4 — shared infra)       │
                              │  · calque-dictionary.json    │
                              │  · empirical-patterns.json   │
                              │  · register-policies         │
                              └──────────────┬──────────────┘
                                             │ read-only
                  ┌──────────────────────────┼──────────────────────────┐
                  ▼                          ▼                          ▼
   ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
   │ arabic-ai-text-      │  │ arabic-corpus-       │  │ arabic-authoring-    │
   │ humanizer            │  │ translator           │  │ suite                │
   │ (v2.7.0 — live)      │  │ (v0.1 — this repo)   │  │ (Q1 2027 — planned)  │
   └──────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

## v0.1 limitations (read before relying on output)

- **Stage A + C only.** Stages B (TM) and D (Validator) are stubs. The current CLI does terminology substitution + LLM draft only.
- **No quality gate.** v0.1 does not detect when output is bad. v0.2 ships the validator + regen loop.
- **No bilingual-corpus mining yet.** The user's `Y:\Linguistics\NewsDataForTranslation\_corpus\parallel\` has 38,886 UUID-aligned pairs ready for ingestion; v0.2 will turn them into a SQLite FTS5 TM.

For production translation today, use this skill **AFTER** human review, not as a replacement.

## Install

Same pattern as the other family skills. Drop into:

- `~/.claude/skills/arabic-corpus-translator/` (user-global)
- `<project>/.claude/skills/arabic-corpus-translator/` (per-project)

Requires `arabic-corpus-toolkit` (v0.4+) discoverable on the filesystem. Default lookup: sibling directory `../arabic-corpus-toolkit`. Override with `ARABIC_CORPUS_TOOLKIT_ROOT` env var.

## License

MIT. See `LICENSE`. Same family-wide license as the humanizer and toolkit.

## See also

- [`arabic-ai-text-humanizer`](https://github.com/drxvb/arabic-ai-text-humanizer) — humanize AI-translated Arabic prose (works as a post-processor for this skill)
- [`arabic-corpus-toolkit`](https://github.com/drxvb/arabic-corpus-toolkit) — shared linguistic infrastructure
