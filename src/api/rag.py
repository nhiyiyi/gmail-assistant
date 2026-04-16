"""BM25-based RAG for Flowmingo scenarios. No external dependencies.

Operates on two separate texts:
  - rules_text    (flowmingo-rules.md)   — always included in full
  - scenarios_text (flowmingo-scenarios.md) — chunked and retrieved by relevance
"""

import re
import math
from collections import Counter


def _tokenize(text: str) -> list:
    return re.findall(r'\b[a-z]{2,}\b', text.lower())


def _bm25(query_tokens: list, doc_token_lists: list, k1: float = 1.5, b: float = 0.75) -> list:
    N = len(doc_token_lists)
    if N == 0:
        return []
    avg_dl = sum(len(d) for d in doc_token_lists) / N or 1
    df = Counter()
    for doc in doc_token_lists:
        for term in set(doc):
            df[term] += 1
    scores = []
    for doc in doc_token_lists:
        dl = len(doc)
        doc_tf = Counter(doc)
        score = 0.0
        for term in query_tokens:
            if term not in df:
                continue
            idf = math.log((N - df[term] + 0.5) / (df[term] + 0.5) + 1)
            tf = doc_tf.get(term, 0)
            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            score += idf * tf_norm
        scores.append(score)
    return scores


def chunk_scenarios(scenarios_text: str) -> list:
    """
    Split scenarios_text into (label, text) chunks.

    Each top-level section (## **N.) and each individual scenario (### **SN)
    becomes a separate retrievable chunk.
    """
    chunks = []
    current_label = None
    current_lines = []

    def flush():
        text = '\n'.join(current_lines).strip()
        if text and current_label:
            chunks.append((current_label, text))

    for line in scenarios_text.split('\n'):
        # Top-level section: ## **N.
        if re.match(r'^## \*\*\d+\.', line):
            flush()
            current_label = re.sub(r'\*+', '', line).strip()
            current_lines = [line]
        # Individual scenario: ### **SN
        elif re.match(r'^### \*\*S\d+', line):
            flush()
            current_label = re.sub(r'\*+', '', line).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    flush()
    return chunks


def get_relevant_context(rules_text: str, scenarios_text: str, email_text: str, top_k: int = 5) -> str:
    """
    Return full rules + top_k most relevant scenario/program chunks for the given email text.

    Typical output: ~1,200 tokens vs ~2,500 for the full combined SOP.
    """
    kb_text, _ = get_relevant_context_with_ids(rules_text, scenarios_text, email_text, top_k)
    return kb_text


def get_relevant_context_with_ids(
    rules_text: str, scenarios_text: str, email_text: str, top_k: int = 5
) -> tuple:
    """
    Same as get_relevant_context but also returns the list of retrieved chunk labels.

    Returns: (kb_text: str, chunk_labels: list[str])
    chunk_labels are the section headers of the top_k retrieved chunks — used by the
    feedback loop to detect retrieval gaps (which sections were NOT retrieved).
    """
    chunks = chunk_scenarios(scenarios_text)

    if not chunks:
        return rules_text, []

    query_tokens = _tokenize(email_text)
    doc_tokens = [_tokenize(label + ' ' + text) for label, text in chunks]
    scores = _bm25(query_tokens, doc_tokens)

    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    top = [chunk for _, chunk in ranked[:top_k]]
    top_labels = [label for label, _ in top]

    retrieved = '\n\n'.join(f'=== {label} ===\n{text}' for label, text in top)
    kb_text = rules_text + '\n\n## RETRIEVED RELEVANT SCENARIOS\n\n' + retrieved
    return kb_text, top_labels
