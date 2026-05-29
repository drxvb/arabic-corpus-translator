# arabic-corpus-translator

> Corpus-grounded EN↔AR translation skill. Uses `arabic-corpus-toolkit` as its terminology base. Four-stage pipeline: terminology → Translation Memory → LLM draft → quality validator. RTL/Arabic-first.

**Status:** **v1.8.0 — stable.** 3-stage pipeline (A → C → D) plus Stage E cross-vendor review and Stage F humanizer quality gate. Stage B (Translation Memory) was dropped after the v0.1.1 corpus-reality check — Asset G's paired terminology and Asset F's mined candidates render TM redundant. Per-call min_consensus filter shipped in v1.8.0 (4-vendor A5 evaluator convergent pick) — consumers can pass `min_consensus=2|3` to restrict to majority-or-unanimous-validated terminology from the toolkit's v1.10.0+ 3-vendor consensus tier.

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
                              │  (v1.12.1 — shared infra)    │
                              │  · 13 assets (A-G.*)         │
                              │  · 4 contracts (G1-G4)       │
                              └──────────────┬──────────────┘
                                             │ read-only
                  ┌──────────────────────────┼──────────────────────────┐
                  ▼                          ▼                          ▼
   ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
   │ arabic-ai-text-      │  │ arabic-corpus-       │  │ arabic-authoring-    │
   │ humanizer            │  │ translator           │  │ suite                │
   │ (v2.16.0 — live)     │  │ (v1.8.0 — this repo) │  │ (v1.6.0 — live)      │
   └──────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

## Current capability (v1.8.0)

- **Stage A** — terminology lookup (calque-dict + Asset F corpus confirmation + Asset G EN↔AR direct pair injection)
- **Stage C** — LLM draft via configurable proxy (kimi/codex/gemini/minimax + arbitrary OpenAI-compatible)
- **Stage D** — validator with calque-rate + term-fidelity + n-gram naturalness scoring; G1 normalize routed through toolkit; regen up to `max_regen` on `verdict=fail`
- **Stage E** — cross-vendor review with auto-correction of safe substring patches; emits `cross_vendor_correction` telemetry
- **Stage F** — humanizer quality gate (`--quality-gate` uses `score_text`; `--deep-quality` uses `score_text_deep` 4-dim cognitive rubric)
- **Influence trace** — every stage emits causal G3 telemetry; consumers get a per-output `influence_trace: [...]` documenting which asset/vendor/rule fired
- **min_consensus filter** (v1.8.0) — pass `translate(text, domain, min_consensus=2)` to filter Asset G terminology hints to majority-validated only

## Install

Same pattern as the other family skills:

- `~/.claude/skills/arabic-corpus-translator/` (user-global)
- `<project>/.claude/skills/arabic-corpus-translator/` (per-project)

Hard dependency on `arabic-corpus-toolkit ≥ v1.5.0` (for G1 normalize contract). Default lookup: sibling directory `../arabic-corpus-toolkit`. Override via `ARABIC_CORPUS_TOOLKIT_ROOT` env var.

## License

MIT. See `LICENSE`. Same family-wide license as the humanizer and toolkit.

## See also

- [`arabic-ai-text-humanizer`](https://github.com/drxvb/arabic-ai-text-humanizer) — humanize AI-translated Arabic prose (works as a post-processor for this skill)
- [`arabic-corpus-toolkit`](https://github.com/drxvb/arabic-corpus-toolkit) — shared linguistic infrastructure
