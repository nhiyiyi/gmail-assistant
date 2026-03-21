# src/persistence — State and Cost Tracking

This directory contains modules that read and write local data files.

## Modules

| File | Writes to |
|------|-----------|
| `state.py` | `stats/email_state.json` — per-email metadata (classification, draft ID, KB version hash) |
| `stats.py` | `stats/email_stats.json`, `stats/email_history.jsonl` — daily cost and token usage |

## Path resolution

Both modules resolve data paths relative to the project root using:
```python
Path(__file__).parent.parent.parent / "stats" / "..."
```
`src/persistence/file.py` → `src/persistence/` → `src/` → project root → `stats/`

Do not change this pattern. The `stats/` directory stays at the project root (it is runtime data, not source code).

## Usage

These modules are imported by `src/api/server.py` via the `sys.path` mechanism — they are not Python packages. Keep them as flat modules with no internal cross-imports.
