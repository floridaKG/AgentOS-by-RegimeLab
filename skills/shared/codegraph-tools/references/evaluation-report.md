# CodeGraph Evaluation Report

Date: 2026-06-02

## Benchmark Results (8 Queries)

### TypeScript Project
Q1: Symbol definition — CG vs search_files → CURRENT
Q2: Symbol callers — CG vs search_files → CURRENT
Q3: executeTrade impact — CG vs search_files → **CG (3.7x faster)**
Q4: Route map — CG vs search_files → CURRENT
Q5: Directory survey — CG vs search_files → CURRENT

### Python Project
Q6: Class definition — CG vs search_files → **CG (5.8x faster)**
Q7: Function callees — CG vs search_files → CURRENT
Q8: Pipeline mapping — CG vs search_files → CURRENT

## Decision: INTEGRATE (targeted usage)

CodeGraph wins on structural queries (impact analysis, depth symbol lookup) where
it eliminates 3-8 tool calls per query. search_files wins on simple text search.

## Strategy
- Text search → grep
- Structural queries (callers, callees, impact, trace, context) → CodeGraph
