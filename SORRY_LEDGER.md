# SORRY_LEDGER.md — juris-calculus

> Track all `sorry`/placeholder usage in JC runtime.
>
> **Rule 1**: Every placeholder or stub must have a ledger entry.
> **Rule 2**: Production code SHALL NOT contain stubs on the critical path.

## Critical-Path Stubs (ZERO stub tolerance)

| # | Component | SPEC |
|---|-----------|------|
| 1 | canonical_adapter | 260 |
| 2 | grounded_evaluator | 260 |
| 3 | certificate_producer | 250 |
| 4 | certificate_checker | 250 |
| 5 | decision_projection | 240 |

## Non-Blocking Stub Entries

| component | SPEC | reason | closing_task | status |
|---|---|---|---|---|

*No entries yet.*
