# Changelog

Corpus-grounded EN↔AR translation skill. Versions track the SKILL.md status banner; this file is the
auditable history (extracted from the inline banner during the A8 audit, 2026-05-29).
Hard dependency: `arabic-corpus-toolkit` (≥ v1.13.0 for `safe_llm_call`; ≥ v1.5.0 for G1-G4 contracts).

## v1.9.0 — LLM provider failure resilience (4/4 A7 convergent must-have)
**Released:** 2026-05-29
Stage C routes through toolkit v1.13.0 `safe_llm_call`: per-call retries (exponential backoff, 2 retries),
per-vendor circuit breaker (3 fails → 60s open), structured failure envelope. Stage C result now includes
`error_class`/`attempts`/`latency_ms`/`circuit_open`. Falls back to legacy inline urllib on pre-v1.13.0
toolkit. Smoke: unreachable endpoint → `ok=False, error_class='network', attempts=3` instead of crashing.
Closes the strongest convergent A7 signal (codex+gemini+minimax+deepseek all #1).

## v1.8.0 — `min_consensus` filtering API
**Released:** 2026-05-29
`translate(text_en, domain, min_consensus=1)` filters Asset G terminology hints by `n_independent_agree`
(toolkit v1.10.0+ 3-vendor tier): 1=all, 2=majority, 3=unanimous. Pre-v1.10.0 assets (G.technology,
G.news) pass through unchanged. Applied at `_find_terminology_pairs_in_text` so it propagates to Stage A,
trace, prompt, and result dict.

## v1.7.0 — G3 telemetry across full pipeline
Extends `InfluenceTrace` to Stages D/E/F (`lex_substitution_fired`, `cross_vendor_correction`,
`humanizer_gate_decision`). Verified: 6 trace records spanning A+D+F on a canonical sentence.

## v1.6.0 — Full G1+G2 adoption
Stage D normalize routes through toolkit `arabic_normalize(level="light")`; all 3 asset loaders use
`_check_asset_compat()` via the registry (legacy `schema_major != "1"` checks removed).

## v1.5.1 — Status-drift correction (banner stuck at v1.3.1)
## v1.5.0 — Stage A wired into G3 `influence_telemetry`
## v1.4.0 — Adopted G2 `asset_registry` (`_check_asset_compat` via `registry.is_compatible()`)
## v1.3.1 — Explicit stderr warning when toolkit not found
## v1.3.0 — Stage F humanizer quality gate (`--quality-gate` / `--deep-quality`)
## v1.2.0 — Native `--llm-proxy {kimi,codex,gemini,minimax}` flag for Stage C
## v1.1.0 — Stage E cross-vendor translation review (safe-substring auto-correction)
## v1.0.1 — Multi-domain Asset G support (`--domain news`)

## v1.0.0 — STABLE: 3-stage pipeline (A → C → D)
Stage B (Translation Memory) **definitively dropped** — the v0.1.1 corpus-reality check found the assumed
bilingual alignment didn't exist (0 paired directories in 77,756); Asset G + Asset F make TM redundant.
Stage A reads three toolkit assets (calque-dictionary A + terminology-candidates F + paired-terminology G).
16/16 eval-suite tests pass.

### Pre-1.0 (summary)
- **v0.3.1** Asset G direct term-pair injection in Stage A · **v0.3.0** Asset F corpus-confirmation signal ·
  **v0.2.3** `ARABIC_CORPUS_TOOLKIT_DISABLE=1` kill-switch · **v0.2.2** Asset C lexical-cleanup in Stage D ·
  **v0.2.1** word-boundary regex fix · **v0.2** working 3-stage pipeline (Option B from corpus reality check).
