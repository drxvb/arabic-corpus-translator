# 01 — Charter

## Mission

Translate English text to Arabic (and, in v0.3+, Arabic to English) using a corpus-grounded pipeline that **defeats the default LLM-translation failure modes** the user has been frustrated by:

- Calques (literal translations that aren't natural Arabic)
- Politically tone-deaf word choices (e.g., "view" → "مشاهدة" in Saudi context)
- Wrong-register vocabulary (using classical for news, news for technical)
- Inconsistent terminology across paragraphs of the same document

## Scope

**In scope:**

- EN → AR translation of news / technical / business / opinion prose (the 4 registers `arabic-ai-text-humanizer` already classifies for)
- AR → EN translation in v0.3+ (less priority — the user's primary need is EN → AR)
- Terminology consistency via the toolkit's calque dictionary
- Translation Memory lookup against the user's SPA bilingual corpus (v0.2+)
- Quality validation via calque-rate / term-fidelity / n-gram naturalness scoring (v0.2+)
- Provider-agnostic LLM integration (OpenAI-compatible endpoint via env vars, same pattern as the humanizer)

**Out of scope (explicitly):**

- **Localization** (BCP47 / ICU / SSML / locale plurals) — separate product category
- **Humanization** of AI-translated output — use `arabic-ai-text-humanizer` as a post-processor
- **Authoring** new content from a brief — use the planned `arabic-authoring-suite`
- **Dialectal translation** (Egyptian, Levantine, Gulf, Maghrebi) — MSA-only by design
- **Literary translation** of fiction / poetry — the calque-detection approach is wrong for literary prose
- **Code documentation translation** — preserve technical English; translating identifiers and code comments breaks code

## The 4-stage pipeline (architectural commitment)

| Stage | Input | Output | v0.1 status |
|---|---|---|---|
| **A — Terminology** | EN text | EN text + per-span calque hints from the toolkit | ✅ stubbed |
| **B — TM lookup** | EN spans | EN→AR pairs from SPA corpus (≥0.85 sim) | ⏳ v0.2 |
| **C — LLM draft** | EN text + Stage A hints + Stage B near-misses | AR draft | ✅ stubbed |
| **D — Validator** | AR draft + toolkit scorers | AR final OR regen request | ⏳ v0.2 |

Each stage is independently testable. v0.1 ships A + C (skeleton); v0.2 ships B + D + the regen loop.

## "Better than corpus baseline" — operationalized

The unfalsifiable user claim "output must be better than shared data" is reframed as **three measurable metrics** (per Agent B):

| Metric | Target | Detector |
|---|---|---|
| **Calque-rate reduction** | ≥60% fewer per 1K tokens vs GPT-4o-class baseline | toolkit's calque dictionary as detector |
| **Term-fidelity** | ≥90% of in-domain terms match `natural_arabic` (not `ai_default_calque`) | toolkit lookup |
| **N-gram naturalness** | Within 1 stddev of human-written news perplexity | `empirical-patterns.json` connector distributions |

Plus an **adversarial 200-sentence set** curated from the user's frustration cases (tech terms, news terms, calque-prone collocations). Per-sentence win/loss vs baseline.

## Anti-scope (what tempts but must be refused)

- **Becoming an MT system.** This is a corpus-grounded specialty translator, not a general-purpose MT engine. Refuse requests for languages outside EN/AR.
- **Mining the LLM-Training-Data corpus uncritically.** Per Agent B, that path is contaminated (may contain AI-translated AR). Mine `News` and `NewsDataForTranslation` first; `LLM-Training-Data` last and quarantined.
- **Caching translations indefinitely.** TM hits can rot (terminology drifts, register changes). Each TM hit carries an age stamp; tighter thresholds for older hits.

## Provenance

Charter derived from Agent B's design doc in the v2.6.0 multi-agent review (`M:\Main\AI\Corpus\humanizer-v2.6-multi-agent-synthesis.md`). Architecture is a direct implementation of Agent B's 4-stage proposal; the operational metrics are Agent B's reframing of the user's unfalsifiable "better than corpus" claim into measurable targets.
