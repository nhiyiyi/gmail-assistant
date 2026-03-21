# src/api — Gmail API Layer

This directory contains the MCP server and Gmail API wrapper.

## Entry point

`server.py` is the MCP server entrypoint. It registers all 17 Gmail tools and starts the stdio server. Run via:
```
python src/api/server.py
```

## Modules

| File | Role |
|------|------|
| `server.py` | MCP server — registers tools, handles requests |
| `gmail_client.py` | Gmail REST API wrapper |
| `labels.py` | Flowmingo label constants |
| `knowledge.py` | Loads SOP `.md` files from `knowledge/` at project root |
| `rag.py` | BM25 keyword retrieval over SOP sections |

## Import mechanism

`server.py` uses `sys.path.insert` to allow bare-name imports of sibling modules and the persistence layer:

```python
sys.path.insert(0, str(Path(__file__).parent))               # src/api/
sys.path.insert(0, str(Path(__file__).parent.parent / "persistence"))  # src/persistence/
```

## Key constraints

- **Never add sending capabilities.** The OAuth scope is `gmail.modify` — drafts only.
- Do not package this as a Python package (no `__init__.py`). The `sys.path` approach is intentional.
- The persistence layer (`state.py`, `stats.py`) lives in `../persistence/` and is loaded via the second `sys.path` entry.
