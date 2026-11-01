# ADR 0002 — Afternoon reference selection (v1.5)

## Status

Accepted

## Context

Owner correction: afternoon FACE RECOGNITION window is 17:00–23:55 (end of minute), not 17:00–19:00.  
18:00 is the preferred reference timestamp for selection, not a capture cutoff.

## Decision

Implement deterministic selection:

1. Exact 18:00 match wins.
2. Else nearest within [ref−5m, ref+5m]; earlier tie-break; then quality; then stable ID.
3. Else latest valid sample before 18:00.
4. Else earliest valid sample after 18:00 (flag AFTERNOON_LATE_FALLBACK).
5. Else no auto event; never fabricate 18:00.

Keep `afternoonFirstObservedAt`, reference, photo, last seen, verified exit as separate fields.  
Approved afternoon leave exempts PM expectation without rewriting observations.

## Consequences

All defaults, migrations, UI labels, tests, reports and mocks use 23:55 end — never 19:00.
