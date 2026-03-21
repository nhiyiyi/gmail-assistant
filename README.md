# Flowmingo Gmail Support Assistant

Reads Flowmingo customer support emails and creates Gmail draft replies using an SOP knowledge base. Drafts appear in your Gmail inbox for human review — nothing is ever auto-sent.

## Prerequisites

- Python 3.10+
- A Google Cloud project with the Gmail API enabled
- Claude Code CLI

## Quick Start

1. **Get OAuth credentials** from Google Cloud Console (detailed steps in `tools/scripts/setup_oauth.py`)
2. Place `credentials.json` at `credentials/credentials.json`
3. **Run OAuth setup:**
   ```
   python tools/scripts/setup_oauth.py
   ```
4. **Open this directory in Claude Code** — the MCP server starts automatically
5. **Process emails:**
   ```
   /process-emails
   ```

## Usage

See [CLAUDE.md](CLAUDE.md) for full usage documentation including:
- Processing emails and refreshing drafts
- Updating the SOP knowledge base
- Cost guidance and model selection
- Hourly auto-run cron setup

## Architecture

See [docs/architecture.md](docs/architecture.md) for a technical overview of the system.
