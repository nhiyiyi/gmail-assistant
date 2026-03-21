"""Loads .md files from the knowledge/ directory."""

from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge"


def load_rules() -> str:
    """Load flowmingo-rules.md — universal rules, always included in full."""
    path = KNOWLEDGE_DIR / "flowmingo-rules.md"
    if not path.exists():
        return "ERROR: flowmingo-rules.md not found in knowledge/."
    return path.read_text(encoding="utf-8")


def load_scenarios() -> str:
    """Load flowmingo-scenarios.md — programs + scenarios, RAG-searched per group."""
    path = KNOWLEDGE_DIR / "flowmingo-scenarios.md"
    if not path.exists():
        return "ERROR: flowmingo-scenarios.md not found in knowledge/."
    return path.read_text(encoding="utf-8")


def load_all() -> str:
    """
    Read every *.md file in knowledge/ and return as a single concatenated string.
    Files are sorted alphabetically for deterministic order.
    """
    if not KNOWLEDGE_DIR.exists():
        return "ERROR: knowledge/ directory not found."

    files = sorted(f for f in KNOWLEDGE_DIR.glob("*.md") if not f.name.startswith("dont-use-"))
    if not files:
        return "ERROR: No .md files found in knowledge/. Add your SOP documents there."

    sections = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            sections.append(f"=== {f.name} ===\n{content}")
        except Exception as e:
            sections.append(f"=== {f.name} ===\nERROR reading file: {e}")

    return "\n\n".join(sections)
