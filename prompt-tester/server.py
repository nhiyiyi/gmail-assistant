#!/usr/bin/env python3
"""
prompt-tester/server.py — Flask prompt tester for the gmail-assistant pipeline.

Run from the prompt-tester/ directory:
    cd Ops/support/gmail-assistant/prompt-tester
    python server.py

Opens at http://localhost:3001
"""

import json
import os
import sys
import time
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────────
TESTER_DIR   = Path(__file__).parent
PROJECT_ROOT = TESTER_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "api"))

import requests
from flask import Flask, jsonify, request, send_from_directory

import rules_engine
import rag
import validators
import scenario_contracts as sc_module
import knowledge

# ── Config ───────────────────────────────────────────────────────────────────
OPENAI_API_URL  = "https://api.openai.com/v1/chat/completions"
MODEL           = "gpt-4.1-mini"
SAMPLES_DIR     = TESTER_DIR / "samples"
KNOWLEDGE_DIR   = PROJECT_ROOT / "knowledge"
RULES_PATH      = KNOWLEDGE_DIR / "flowmingo-rules.md"
SCENARIOS_PATH  = KNOWLEDGE_DIR / "flowmingo-scenarios.md"
RULES_BAK       = TESTER_DIR / "flowmingo-rules.bak.md"
SCENARIOS_BAK   = TESTER_DIR / "flowmingo-scenarios.bak.md"
PORT            = 3001

# ── Backup SOP files on startup ──────────────────────────────────────────────
import shutil
for src, bak in [(RULES_PATH, RULES_BAK), (SCENARIOS_PATH, SCENARIOS_BAK)]:
    if not bak.exists() and src.exists():
        shutil.copy2(src, bak)
        print(f"  Backed up {src.name} -> {bak.name}")

# ── Load pipeline modules ─────────────────────────────────────────────────────
def _reload_knowledge():
    import importlib
    importlib.reload(knowledge)
    importlib.reload(rag)

# ── Import pipeline prompts from batch_test ───────────────────────────────────
# Add tools/scripts to path to import NODE1/NODE2 prompts
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "scripts"))
try:
    import batch_test as _bt
    NODE1_CLASSIFIER_SCHEMA = _bt.NODE1_CLASSIFIER_SCHEMA
    NODE2_DRAFT_RULES       = _bt.NODE2_DRAFT_RULES
    _build_node1_prompt     = _bt.build_node1_prompt
    _build_node2_prompt     = _bt.build_node2_prompt
    _call_openai            = _bt.call_openai
except Exception as e:
    print(f"WARN: could not import batch_test: {e}")
    NODE1_CLASSIFIER_SCHEMA = ""
    NODE2_DRAFT_RULES       = ""

# ── Markdown → HTML converter (mirrors gmail_client._markdown_to_html) ────────
import re as _re
from html import escape as _esc

_STEP_START = '\x00STEPS\x00'
_STEP_END   = '\x00ENDSTEPS\x00'

_ABBREV_PROTECT = _re.compile(
    r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e|No|Vol)\.',
    _re.IGNORECASE,
)
_SENT_BOUNDARY = _re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


def _split_sentences(text: str) -> list:
    """Split text into sentences, protecting common abbreviations."""
    protected = _ABBREV_PROTECT.sub(lambda m: m.group(0).replace('.', '\x01'), text)
    parts = _SENT_BOUNDARY.split(protected)
    return [p.replace('\x01', '.') for p in parts]


def _split_long_paragraphs(text: str, max_sentences: int = 2) -> str:
    """Break paragraphs that contain more than max_sentences sentences."""
    paragraphs = text.split('\n\n')
    out = []
    for para in paragraphs:
        stripped = para.strip()
        if (not stripped
                or stripped.startswith('- ')
                or '\x00' in stripped
                or stripped.startswith('[REVIEW')
                or '\n' in stripped):
            out.append(para)
            continue
        sentences = _split_sentences(stripped)
        if len(sentences) <= max_sentences:
            out.append(para)
        else:
            chunks = []
            for i in range(0, len(sentences), max_sentences):
                chunks.append(' '.join(sentences[i:i + max_sentences]))
            out.append('\n\n'.join(chunks))
    return '\n\n'.join(out)

# Patterns to auto-bold when the LLM omits **bold** in key contexts
_AUTO_BOLD_PATTERNS = [
    # Timeframes
    (_re.compile(r'\b(within \d[–\-]\d+ (?:business )?(?:days?|weeks?|hours?))\b', _re.I), r'**\1**'),
    (_re.compile(r'\b(\d[–\-]\d+ (?:business )?(?:days?|weeks?|hours?))\b', _re.I), r'**\1**'),
    # WhatsApp contact
    (_re.compile(r'(\+\d[\d\s\(\)\-]{6,})', _re.I), r'**\1**'),
    (_re.compile(r'\b(WhatsApp)\b'), r'**\1**'),
    # Key platforms/actions
    (_re.compile(r'\b(G2|Capterra)\b'), r'**\1**'),
    # Confirmation form action (offer letter replies)
    (_re.compile(r'(the confirmation link in your offer email)', _re.I), r'**\1**'),
    (_re.compile(r'(confirmation form)', _re.I), r'**\1**'),
    # Calendar booking
    (_re.compile(r'(https://calendar\.app\.google/\S+)'), r'**\1**'),
    # Training resources
    (_re.compile(r'(Training [Dd]eck|Quickstart [Gg]uide|training materials)', _re.I), r'**\1**'),
]


def _auto_bold_key_info(text: str) -> str:
    """Add **bold** to key info patterns only when the draft has no bold at all."""
    if '**' in text:
        return text  # LLM already used bold — don't interfere
    for pattern, replacement in _AUTO_BOLD_PATTERNS:
        new_text = pattern.sub(replacement, text, count=1)
        if new_text != text:
            return new_text  # Stop after first successful auto-bold
    return text

def _auto_bulletize_steps(text: str) -> str:
    """
    Detect LLM step patterns (lead-in line ending with ':' followed by 2+ unlabelled
    lines) and wrap them in step-block markers so they render as a styled callout.
    """
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if stripped.endswith(':') and not stripped.startswith('-'):
            j = i + 1
            candidates = []
            while j < len(lines) and lines[j].strip():
                candidates.append(lines[j])
                j += 1
            if len(candidates) >= 2 and not any(c.startswith('- ') for c in candidates):
                result.append(line)
                result.append(_STEP_START)
                for c in candidates:
                    m = _re.match(r'^([A-Z][^:]{2,40}):\s+(.+)$', c)
                    if m:
                        result.append(f'- **{m.group(1)}:** {m.group(2)}')
                    else:
                        result.append(f'- {c}')
                result.append(_STEP_END)
                i = j
                continue
        result.append(line)
        i += 1
    return '\n'.join(result)


def _step_blocks_to_callout(t: str) -> str:
    """Convert step-block markers into a styled blue callout box."""
    def _make_callout(m):
        inner = m.group(1)
        items_html = ''
        for line in inner.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                items_html += f'<li style="margin:5px 0">{line[2:]}</li>'
        return (
            '<div style="background:#EBF5FB;border-left:4px solid #2E86C1;'
            'border-radius:0 4px 4px 0;padding:12px 16px;margin:12px 0">'
            '<div style="font-weight:700;color:#1A5276;margin-bottom:8px;font-size:13px">'
            '\U0001f6e0\ufe0f Try these steps</div>'
            f'<ul style="margin:0;padding-left:20px;color:#1a1a1a">{items_html}</ul>'
            '</div>'
        )
    return _re.sub(
        _re.escape(_STEP_START) + r'(.*?)' + _re.escape(_STEP_END),
        _make_callout,
        t,
        flags=_re.DOTALL,
    )


def _markdown_to_html(text: str) -> str:
    """Convert LLM markdown to HTML for preview. Mirrors gmail_client._markdown_to_html."""
    # 0a. Break paragraphs longer than 2 sentences
    text = _split_long_paragraphs(text, max_sentences=2)
    # 0b. Auto-bold key info if LLM produced no bold at all
    text = _auto_bold_key_info(text)
    # 0c. Detect unlabelled step lists and wrap in step-block markers
    text = _auto_bulletize_steps(text)
    # 1. HTML-escape (markers use \x00 so they survive HTML escaping untouched)
    t = _esc(text)
    # 2. [REVIEW NEEDED: msg] → amber banner
    t = _re.sub(
        r'\[REVIEW NEEDED:\s*(.*?)\]',
        lambda m: f'<div style="background:#FFF3CD;padding:8px 12px;border-left:4px solid #FFC107;margin:8px 0">\u26a0 {m.group(1)}</div>',
        t,
    )
    # 3. **bold** → <strong> (runs inside step blocks too)
    t = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    # 4. Step blocks → styled blue callout (before generic bullet conversion)
    t = _step_blocks_to_callout(t)
    # 5. Remaining "- " bullet blocks → plain <ul>
    def _bulletize(m):
        items = _re.sub(r'(?m)^- (.*)', r'<li>\1</li>', m.group(0))
        return '<ul style="margin:8px 0 8px 20px;padding:0">' + items + '</ul>'
    t = _re.sub(r'(?m)(?:^- .+\n?)+', _bulletize, t)
    # 6. Blank lines → paragraph breaks
    t = _re.sub(r'\n\n+', '<br><br>', t)
    # 7. Remaining single newlines → <br>
    t = t.replace('\n', '<br>')
    return t


def _render_email_html(draft_body: str) -> str:
    """Wrap draft body in an email-style container."""
    body_html = _markdown_to_html(draft_body)
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;
max-width:600px;margin:0 auto;padding:20px;border:1px solid #e0e0e0;border-radius:4px">
{body_html}
</div>"""


# ── OpenAI call ───────────────────────────────────────────────────────────────
def call_openai_safe(api_key, system_prompt, user_prompt, max_tokens=1200):
    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            },
            timeout=90,
        )
        if resp.status_code == 429:
            return {"apiError": "rate_limited", "retry_after_seconds": 60}
        if resp.status_code == 401:
            return {"apiError": "invalid_api_key"}
        resp.raise_for_status()
        body = resp.json()
        usage = body.get("usage", {})
        text  = body["choices"][0]["message"]["content"].strip()
        return {
            "result": json.loads(text),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }
    except requests.exceptions.Timeout:
        return {"apiError": "timeout", "retry_after_seconds": 30}
    except json.JSONDecodeError as e:
        return {"parseError": str(e), "raw": text if 'text' in dir() else ""}
    except Exception as e:
        return {"apiError": str(e)}


# ── Full pipeline run ─────────────────────────────────────────────────────────
def run_pipeline(sample: dict, api_key: str, rules_override: str = None, scenarios_override: str = None) -> dict:
    t0 = time.time()
    email = dict(sample)
    email["has_support_reply"] = False   # same override as batch_test.py

    # 1. rules_engine
    route = rules_engine.route(email)
    email.update({
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "latest_message": email.get("latest_message", "") or email.get("latestText", ""),
        "thread_context": email.get("thread_context", ""),
        "message_count": email.get("message_count", 1),
        "attachments": email.get("attachments", []),
        "has_attachments": bool(email.get("attachments")),
    })
    pre_hint = route.get("pre_route_hint", "unclear")
    risk_triggers = list(route.get("risk_triggers", []))

    # 2. BM25 RAG — use override text if provided
    rules_text     = rules_override or RULES_PATH.read_text(encoding="utf-8")
    scenarios_text = scenarios_override or SCENARIOS_PATH.read_text(encoding="utf-8")
    email_text     = email.get("latest_message", "") or email.get("subject", "")
    kb_text, _     = rag.get_relevant_context_with_ids(
        rules_text=rules_text,
        scenarios_text=scenarios_text,
        email_text=email_text,
        top_k=5,
    )

    # 3. Node 1
    n1_sys, n1_usr = _build_node1_prompt(email)
    n1_resp = call_openai_safe(api_key, n1_sys, n1_usr, max_tokens=600)
    if "apiError" in n1_resp:
        return {"error": n1_resp, "rules_engine": route, "duration_ms": int((time.time()-t0)*1000)}

    node1 = n1_resp.get("result", {})

    # 4. Contracts
    contracts = sc_module.load_all()
    scenario_id = node1.get("scenario", "FALLBACK")
    contract, extra_triggers = sc_module.select(contracts, pre_hint, scenario_id)
    risk_triggers.extend(extra_triggers)

    # 5. Node 2
    email_body_len = len(email.get("latest_message", ""))
    n2_max_tokens = min(max(2000, email_body_len // 3 + 600), 4000)
    n2_sys, n2_usr = _build_node2_prompt(email, kb_text, node1, scenarios_text=scenarios_text)
    n2_resp = call_openai_safe(api_key, n2_sys, n2_usr, max_tokens=n2_max_tokens)
    if "apiError" in n2_resp:
        return {"error": n2_resp, "rules_engine": route, "node1": node1, "duration_ms": int((time.time()-t0)*1000)}

    node2 = n2_resp.get("result", {})
    draft_raw = node2.get("draft_body", "")

    # 6. Validate + auto-fix
    val = validators.validate(draft_raw, contract, risk_triggers)
    draft_fixed = val.get("fixed_draft", draft_raw)

    duration_ms = int((time.time() - t0) * 1000)
    return {
        "rules_engine": route,
        "node1": node1,
        "node2_raw": node2,
        "draft_raw": draft_raw,
        "draft_fixed": draft_fixed,
        "draft_html": _render_email_html(draft_fixed),
        "validation": val,
        "scenario_id": scenario_id,
        "contract_used": contract.get("scenario_id", "FALLBACK"),
        "n1_tokens": {"in": n1_resp.get("input_tokens", 0), "out": n1_resp.get("output_tokens", 0)},
        "n2_tokens": {"in": n2_resp.get("input_tokens", 0), "out": n2_resp.get("output_tokens", 0)},
        "duration_ms": duration_ms,
    }


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(TESTER_DIR))

@app.route("/")
def index():
    return send_from_directory(TESTER_DIR, "index.html")


@app.route("/samples")
def list_samples():
    if not SAMPLES_DIR.exists():
        return jsonify([])
    names = sorted(f.stem for f in SAMPLES_DIR.glob("sample-*.json"))
    return jsonify(names)


@app.route("/prompt", methods=["GET", "POST"])
def prompt_rules():
    if request.method == "GET":
        return jsonify({"content": RULES_PATH.read_text(encoding="utf-8") if RULES_PATH.exists() else ""})
    data = request.get_json(force=True)
    RULES_PATH.write_text(data.get("content", ""), encoding="utf-8")
    _reload_knowledge()
    return jsonify({"ok": True})


@app.route("/prompt2", methods=["GET", "POST"])
def prompt_scenarios():
    if request.method == "GET":
        return jsonify({"content": SCENARIOS_PATH.read_text(encoding="utf-8") if SCENARIOS_PATH.exists() else ""})
    data = request.get_json(force=True)
    SCENARIOS_PATH.write_text(data.get("content", ""), encoding="utf-8")
    _reload_knowledge()
    return jsonify({"ok": True})


@app.route("/run", methods=["POST"])
def run_sample():
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return jsonify({"apiError": "OPENAI_API_KEY not set"}), 400

    body = request.get_json(force=True)
    sample_id = Path(body.get("sample_name", "")).name  # sanitize path traversal
    if not sample_id:
        return jsonify({"error": "sample_name required"}), 400

    sample_path = SAMPLES_DIR / f"{sample_id}.json"
    if not sample_path.exists():
        return jsonify({"error": f"Sample not found: {sample_id}"}), 404

    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    result = run_pipeline(sample, api_key)
    return jsonify(result)


@app.route("/run-both", methods=["POST"])
def run_both():
    """Run pipeline with bak (original) SOP and current SOP side-by-side."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return jsonify({"apiError": "OPENAI_API_KEY not set"}), 400

    body = request.get_json(force=True)
    sample_id = Path(body.get("sample_name", "")).name
    if not sample_id:
        return jsonify({"error": "sample_name required"}), 400

    sample_path = SAMPLES_DIR / f"{sample_id}.json"
    if not sample_path.exists():
        return jsonify({"error": f"Sample not found: {sample_id}"}), 404

    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    # Old = bak files
    old_rules     = RULES_BAK.read_text(encoding="utf-8") if RULES_BAK.exists() else None
    old_scenarios = SCENARIOS_BAK.read_text(encoding="utf-8") if SCENARIOS_BAK.exists() else None

    old_result = run_pipeline(sample, api_key, rules_override=old_rules, scenarios_override=old_scenarios)
    new_result = run_pipeline(sample, api_key)

    return jsonify({"old": old_result, "new": new_result})


if __name__ == "__main__":
    print(f"Prompt tester running at http://localhost:{PORT}")
    print(f"Samples: {len(list(SAMPLES_DIR.glob('sample-*.json'))) if SAMPLES_DIR.exists() else 0}")
    print(f"Contracts: {len(sc_module.load_all())}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
