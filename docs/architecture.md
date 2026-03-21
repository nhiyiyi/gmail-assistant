# Architecture

## Overview

The assistant runs as an MCP (Model Context Protocol) server that exposes Gmail tools to Claude Code. When Claude processes emails, it calls these tools to read emails, load the SOP, create drafts, and track state.

## Data Flow

```
Gmail API
    ↓
src/api/gmail_client.py   — REST API wrapper (list, get, draft, label, mark-read)
    ↓
src/api/server.py         — MCP server, 17 tools registered here
    ↓                            ↑
src/api/knowledge.py      — loads knowledge/ SOP markdown files
src/api/rag.py            — BM25 keyword retrieval (get_kb_for_email)
    ↓
Claude (via Claude Code)  — classifies email, writes reply using SOP
    ↓
src/persistence/state.py  — writes per-email metadata to stats/email_state.json
src/persistence/stats.py  — writes cost/token usage to stats/email_stats.json
```

## Module Split

### `src/api/` — Gmail API and MCP server layer

| File | Role |
|------|------|
| `server.py` | MCP entrypoint — registers all 17 tools, starts stdio server |
| `gmail_client.py` | Gmail REST API wrapper — list, get, thread, draft, label, mark-read |
| `labels.py` | Flowmingo label constants (FM/ready, FM/review, FM/no-reply) |
| `knowledge.py` | Loads all `.md` files from `knowledge/` into context |
| `rag.py` | BM25 keyword search over SOP sections for relevant snippets |

### `src/persistence/` — Local state and cost tracking

| File | Role |
|------|------|
| `state.py` | Per-email state: classification, draft ID, KB version hash |
| `stats.py` | Daily cost tracking, token usage, processing history |

Both modules resolve their data paths via `Path(__file__).parent.parent.parent / "stats/"` — pointing to the `stats/` directory at the project root.

## Email Classification (Three-Tier)

Every email is classified into one of three tiers:

- **FM/ready** — clear SOP match, confident reply, draft ready to send
- **FM/review** — ambiguous, sensitive, or no SOP match — draft prefixed with `[REVIEW NEEDED: <reason>]`
- **FM/no-reply** — automated sender, newsletter, or thread already replied — no draft created

## MCP Server

The server starts automatically via `.mcp.json` when opening this directory in Claude Code:

```json
{"mcpServers": {"gmail": {"command": "python", "args": ["src/api/server.py"]}}}
```

The server uses `sys.path` manipulation (not Python packaging) to import sibling modules — `src/api/` is added for the API layer and `src/persistence/` is added for the persistence layer.

## Knowledge / RAG Pipeline

1. `knowledge/flowmingo-sop.md` (and any other `.md` files in `knowledge/`) are loaded at server start
2. `get_kb_for_email` uses BM25 to retrieve the most relevant SOP sections for a given email
3. Relevant snippets are passed to Claude as context when drafting replies
4. A SHA-256 hash of the full KB is stored per draft — used by `/refresh-drafts` to detect stale drafts after SOP edits

## OAuth Scope

The OAuth token uses `gmail.modify` scope — this allows reading, labeling, and drafting but **cannot send email**. Sending is architecturally impossible.
