# wrapper/fallback/ — deterministic no-LLM fallbacks

Everything here exists so the demo runs end to end **without** an LLM key: when
the LLM router/enricher is unavailable or returns something unusable, the
pipeline falls back to these deterministic heuristics.

- `routing.py` — `fallback_route()`: keyword-hint retailer routing (stand-in for
  the `translate` stage's LLM router).
- `colors.py` — `fallback_colors()`: canned color options (stand-in for the
  `enhance` stage's LLM color enrichment).

## Removing it in one go (when the LLM path is reliable)

1. Delete this folder: `rm -rf wrapper/fallback`
2. In `wrapper/pipeline.py`, remove the two `# [FALLBACK]` blocks (each is a
   small, clearly marked `if`/loop) and the
   `from .fallback import fallback_route, fallback_colors` import.

Nothing else imports this package, so those are the only edits needed. After
that, an unavailable LLM surfaces as a real error instead of silently degrading.
