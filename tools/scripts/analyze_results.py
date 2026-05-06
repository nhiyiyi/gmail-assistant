#!/usr/bin/env python3
"""
analyze_results.py — Compare baseline vs new batch_test.py results.

Reads results/baseline/ and results/new/, produces a side-by-side HTML
comparison report at results/comparison_report.html.

Usage:
    python tools/scripts/analyze_results.py
    python tools/scripts/analyze_results.py --baseline results/baseline/ --new results/new/
    python tools/scripts/analyze_results.py --open
"""

import argparse
import json
import sys
from pathlib import Path
from html import escape

SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
RESULTS_ROOT = PROJECT_ROOT / "prompt-tester" / "results"


# ── Load helpers ─────────────────────────────────────────────────────────────

def load_dir(dirpath: Path) -> dict[str, dict]:
    """Load all sample-*.json files from a results directory. Returns {sample_name: data}."""
    results = {}
    for f in sorted(dirpath.glob("sample-*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("sample_name") or f.stem
            results[name] = data
        except Exception as e:
            print(f"  WARN: could not parse {f.name}: {e}", file=sys.stderr)
    return results


def get_scenario(data: dict) -> str:
    return (data.get("node1") or {}).get("scenario") or "?"


def get_expected(data: dict) -> str:
    return data.get("expected_scenario") or "?"


def get_severity(data: dict) -> str:
    return (data.get("validation") or {}).get("severity") or "?"


def is_correct(data: dict) -> bool:
    return bool(data.get("scenario_correct"))


def get_draft(data: dict) -> str:
    return data.get("draft_fixed") or data.get("draft_raw") or ""


def get_label(data: dict) -> str:
    return data.get("label") or "?"


def severity_class(sev: str) -> str:
    return {
        "PASS": "sev-pass",
        "LOW": "sev-low",
        "MEDIUM": "sev-medium",
        "HIGH": "sev-high",
    }.get(sev, "sev-unknown")


def correct_class(correct: bool) -> str:
    return "correct" if correct else "wrong"


# ── Summary stats ─────────────────────────────────────────────────────────────

def compute_stats(results: dict) -> dict:
    total = len(results)
    if total == 0:
        return {"total": 0, "correct": 0, "accuracy": 0, "severity": {}, "s8_count": 0, "label_dist": {}}

    correct = sum(1 for d in results.values() if is_correct(d))
    s8_count = sum(1 for d in results.values() if get_scenario(d) == "S8")
    severity_dist: dict[str, int] = {}
    label_dist: dict[str, int] = {}
    for d in results.values():
        sev = get_severity(d)
        severity_dist[sev] = severity_dist.get(sev, 0) + 1
        lbl = get_label(d)
        label_dist[lbl] = label_dist.get(lbl, 0) + 1

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(100 * correct / total, 1),
        "severity": severity_dist,
        "s8_count": s8_count,
        "label_dist": label_dist,
    }


def wrong_scenario_dist(results: dict) -> dict[str, int]:
    dist: dict[str, int] = {}
    for d in results.values():
        if not is_correct(d):
            got = get_scenario(d)
            dist[got] = dist.get(got, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


# ── HTML generation ──────────────────────────────────────────────────────────

CSS = """
body { font-family: Arial, sans-serif; font-size: 13px; color: #222; margin: 20px; }
h1 { color: #1a1a2e; }
h2 { color: #16213e; border-bottom: 2px solid #e8e8e8; padding-bottom: 6px; }
.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
.stat-box { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 16px; }
.stat-box h3 { margin: 0 0 10px 0; font-size: 14px; color: #495057; }
.big-num { font-size: 36px; font-weight: bold; color: #1a1a2e; }
.delta { font-size: 14px; margin-left: 8px; }
.delta-pos { color: #28a745; }
.delta-neg { color: #dc3545; }
.delta-neu { color: #6c757d; }
table { width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 12px; }
th { background: #343a40; color: white; padding: 8px 10px; text-align: left; }
td { padding: 6px 10px; border-bottom: 1px solid #dee2e6; vertical-align: top; }
tr:hover { background: #f8f9fa; }
.correct { color: #28a745; font-weight: bold; }
.wrong { color: #dc3545; font-weight: bold; }
.sev-pass { color: #28a745; }
.sev-low { color: #17a2b8; }
.sev-medium { color: #fd7e14; font-weight: bold; }
.sev-high { color: #dc3545; font-weight: bold; }
.sev-unknown { color: #6c757d; }
.draft-cell { max-width: 300px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 11px; color: #555; cursor: pointer; }
.draft-cell:hover { white-space: normal; overflow: visible; background: #fffde7; z-index: 10; position: relative; }
.scenario-match { background: #e8f5e9; }
.scenario-improved { background: #e3f2fd; }
.scenario-regressed { background: #fff3e0; }
.scenario-unchanged-wrong { background: #fce4ec; }
.tag { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: bold; }
.tag-improved { background: #d4edda; color: #155724; }
.tag-regressed { background: #f8d7da; color: #721c24; }
.tag-same { background: #d1ecf1; color: #0c5460; }
.tag-new { background: #fff3cd; color: #856404; }
.section-divider { margin: 40px 0 20px 0; border-top: 3px solid #343a40; }
.no-data { color: #6c757d; font-style: italic; }
"""

JS = """
function toggleDraft(el) {
    el.classList.toggle('expanded');
}
"""


def fmt_sev(sev: str) -> str:
    return f'<span class="{severity_class(sev)}">{escape(sev)}</span>'


def fmt_correct(correct: bool, expected: str, got: str) -> str:
    if correct:
        return f'<span class="correct">[OK] {escape(got)}</span>'
    return f'<span class="wrong">[!] {escape(got)} (exp {escape(expected)})</span>'


def stat_row(label: str, base_val, new_val, pct: bool = False, invert: bool = False) -> str:
    """Single stat row comparing baseline vs new."""
    if pct:
        base_str = f"{base_val}%"
        new_str = f"{new_val}%"
        diff = new_val - base_val
    else:
        base_str = str(base_val)
        new_str = str(new_val)
        diff = new_val - base_val if isinstance(new_val, (int, float)) and isinstance(base_val, (int, float)) else None

    delta_str = ""
    if diff is not None:
        sign = "+" if diff > 0 else ""
        if invert:
            cls = "delta-pos" if diff < 0 else ("delta-neg" if diff > 0 else "delta-neu")
        else:
            cls = "delta-pos" if diff > 0 else ("delta-neg" if diff < 0 else "delta-neu")
        suffix = "%" if pct else ""
        delta_str = f'<span class="delta {cls}">({sign}{diff}{suffix})</span>'

    return f"""
<tr>
  <td><b>{escape(label)}</b></td>
  <td>{escape(base_str)}</td>
  <td>{escape(new_str)} {delta_str}</td>
</tr>"""


def generate_html(
    baseline: dict,
    new: dict,
    base_stats: dict,
    new_stats: dict,
    common_keys: list[str],
    only_new: list[str],
    only_base: list[str],
) -> str:
    # Categorize common samples
    improved = [k for k in common_keys if not is_correct(baseline[k]) and is_correct(new[k])]
    regressed = [k for k in common_keys if is_correct(baseline[k]) and not is_correct(new[k])]
    still_wrong = [k for k in common_keys if not is_correct(baseline[k]) and not is_correct(new[k])]
    both_correct = [k for k in common_keys if is_correct(baseline[k]) and is_correct(new[k])]

    # Severity changes
    sev_improved = [
        k for k in common_keys
        if get_severity(baseline[k]) in ("MEDIUM", "HIGH")
        and get_severity(new[k]) in ("PASS", "LOW")
    ]

    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Batch Test Comparison Report</title>
<style>{CSS}</style>
<script>{JS}</script>
</head>
<body>
<h1>Batch Test Comparison Report</h1>
<p>Baseline: <b>{base_stats['total']}</b> samples &nbsp;|&nbsp; New: <b>{new_stats['total']}</b> samples &nbsp;|&nbsp; Common: <b>{len(common_keys)}</b></p>
"""]

    # Summary grid
    parts.append('<div class="summary-grid">')
    parts.append(f"""
<div class="stat-box">
  <h3>Scenario Accuracy</h3>
  <div><span class="big-num">{new_stats['accuracy']}%</span>
    <span class="delta {'delta-pos' if new_stats['accuracy'] > base_stats['accuracy'] else 'delta-neg'}">
      ({'+' if new_stats['accuracy'] >= base_stats['accuracy'] else ''}{round(new_stats['accuracy'] - base_stats['accuracy'], 1)}%)
    </span>
  </div>
  <div style="color:#888;font-size:11px;margin-top:4px">Baseline: {base_stats['accuracy']}%</div>
</div>
""")
    parts.append(f"""
<div class="stat-box">
  <h3>S8 Over-Classification</h3>
  <div><span class="big-num">{new_stats['s8_count']}</span>
    <span class="delta {'delta-pos' if new_stats['s8_count'] < base_stats['s8_count'] else 'delta-neg'}">
      ({'+' if new_stats['s8_count'] >= base_stats['s8_count'] else ''}{new_stats['s8_count'] - base_stats['s8_count']})
    </span>
  </div>
  <div style="color:#888;font-size:11px;margin-top:4px">Baseline: {base_stats['s8_count']}</div>
</div>
""")
    parts.append(f"""
<div class="stat-box">
  <h3>Sample Changes (common {len(common_keys)})</h3>
  <div style="color:#28a745">&#9650; Improved: {len(improved)}</div>
  <div style="color:#dc3545">&#9660; Regressed: {len(regressed)}</div>
  <div style="color:#fd7e14">Still wrong: {len(still_wrong)}</div>
  <div style="color:#28a745">Both correct: {len(both_correct)}</div>
</div>
""")
    sev_items = "".join(f"<div><b>{k}:</b> {base_stats['severity'].get(k, 0)} &rarr; {new_stats['severity'].get(k, 0)}</div>"
                        for k in ["PASS", "LOW", "MEDIUM", "HIGH"])
    parts.append(f"""
<div class="stat-box">
  <h3>Severity Distribution</h3>
  {sev_items}
</div>
""")
    parts.append('</div>')  # end summary-grid

    # Stats comparison table
    parts.append('<h2>Stats Comparison</h2>')
    parts.append('<table><tr><th>Metric</th><th>Baseline</th><th>New</th></tr>')
    parts.append(stat_row("Samples", base_stats["total"], new_stats["total"]))
    parts.append(stat_row("Correct", base_stats["correct"], new_stats["correct"]))
    parts.append(stat_row("Accuracy", base_stats["accuracy"], new_stats["accuracy"], pct=True))
    parts.append(stat_row("S8 count", base_stats["s8_count"], new_stats["s8_count"], invert=True))
    for sev in ["PASS", "LOW", "MEDIUM", "HIGH"]:
        b = base_stats["severity"].get(sev, 0)
        n = new_stats["severity"].get(sev, 0)
        inv = sev in ("MEDIUM", "HIGH")
        parts.append(stat_row(f"Severity {sev}", b, n, invert=inv))
    parts.append('</table>')

    # Wrong scenario distribution
    base_wrong_dist = wrong_scenario_dist(baseline)
    new_wrong_dist = wrong_scenario_dist(new)
    if base_wrong_dist or new_wrong_dist:
        all_wrong_scen = sorted(set(list(base_wrong_dist.keys()) + list(new_wrong_dist.keys())),
                                key=lambda x: -base_wrong_dist.get(x, 0))
        parts.append('<h2>Wrong Scenario Distribution (what the model chose instead)</h2>')
        parts.append('<table><tr><th>Wrong Scenario</th><th>Baseline Count</th><th>New Count</th></tr>')
        for s in all_wrong_scen[:15]:
            b = base_wrong_dist.get(s, 0)
            n = new_wrong_dist.get(s, 0)
            delta = n - b
            sign = "+" if delta > 0 else ""
            cls = "delta-neg" if delta > 0 else "delta-pos"
            parts.append(f'<tr><td>{escape(s)}</td><td>{b}</td><td>{n} <span class="delta {cls}">({sign}{delta})</span></td></tr>')
        parts.append('</table>')

    # ── Improvements ──
    if improved:
        parts.append('<div class="section-divider"></div>')
        parts.append(f'<h2>&#9650; Improvements ({len(improved)} samples now correct)</h2>')
        parts.append(_sample_table(improved, baseline, new, tag="tag-improved", tag_label="IMPROVED"))

    # ── Regressions ──
    if regressed:
        parts.append('<div class="section-divider"></div>')
        parts.append(f'<h2>&#9660; Regressions ({len(regressed)} samples — was correct, now wrong)</h2>')
        parts.append(_sample_table(regressed, baseline, new, tag="tag-regressed", tag_label="REGRESSED"))

    # ── Still wrong ──
    if still_wrong:
        parts.append('<div class="section-divider"></div>')
        parts.append(f'<h2>Still Failing ({len(still_wrong)} samples)</h2>')
        parts.append(_sample_table(still_wrong, baseline, new, tag="tag-same", tag_label="UNCHANGED"))

    # ── New samples only ──
    if only_new:
        parts.append('<div class="section-divider"></div>')
        parts.append(f'<h2>New-Only Samples ({len(only_new)} — no baseline to compare)</h2>')
        parts.append(_new_only_table(only_new, new))

    # ── Both correct ──
    if both_correct:
        parts.append('<div class="section-divider"></div>')
        details_id = "both-correct-details"
        parts.append(f'<h2>Both Correct ({len(both_correct)} samples)</h2>')
        parts.append(f'<details id="{details_id}"><summary>Expand {len(both_correct)} correct samples</summary>')
        parts.append(_sample_table(both_correct, baseline, new, tag="tag-same", tag_label="CORRECT"))
        parts.append('</details>')

    parts.append('</body></html>')
    return "\n".join(parts)


def _sample_table(sample_names: list, baseline: dict, new: dict,
                  tag: str = "", tag_label: str = "") -> str:
    rows = ['<table><tr><th>Sample</th><th>Expected</th>'
            '<th>Baseline Scenario</th><th>New Scenario</th>'
            '<th>Base Sev</th><th>New Sev</th>'
            '<th>Baseline Draft (hover)</th><th>New Draft (hover)</th></tr>']

    for name in sample_names:
        base_d = baseline.get(name, {})
        new_d  = new.get(name, {})

        exp     = get_expected(new_d) or get_expected(base_d)
        base_sc = get_scenario(base_d) if base_d else "-"
        new_sc  = get_scenario(new_d)  if new_d  else "-"
        base_correct = is_correct(base_d) if base_d else False
        new_correct  = is_correct(new_d)  if new_d  else False
        base_sev = get_severity(base_d) if base_d else "-"
        new_sev  = get_severity(new_d)  if new_d  else "-"
        base_draft = get_draft(base_d)[:500] if base_d else ""
        new_draft  = get_draft(new_d)[:500]  if new_d  else ""

        tag_html = f'<span class="tag {tag}">{escape(tag_label)}</span> ' if tag else ""
        short_name = name[:50] + "..." if len(name) > 50 else name

        rows.append(f"""<tr>
<td>{tag_html}<small>{escape(short_name)}</small></td>
<td><b>{escape(exp)}</b></td>
<td class="{correct_class(base_correct)}">{escape(base_sc)}</td>
<td class="{correct_class(new_correct)}">{escape(new_sc)}</td>
<td>{fmt_sev(base_sev)}</td>
<td>{fmt_sev(new_sev)}</td>
<td class="draft-cell" title="{escape(base_draft)}">{escape(base_draft[:120])}</td>
<td class="draft-cell" title="{escape(new_draft)}">{escape(new_draft[:120])}</td>
</tr>""")

    rows.append('</table>')
    return "\n".join(rows)


def _new_only_table(sample_names: list, new: dict) -> str:
    rows = ['<table><tr><th>Sample</th><th>Expected</th>'
            '<th>Scenario</th><th>Correct?</th><th>Severity</th>'
            '<th>Draft (hover)</th></tr>']

    for name in sample_names:
        d = new.get(name, {})
        exp  = get_expected(d)
        sc   = get_scenario(d)
        corr = is_correct(d)
        sev  = get_severity(d)
        draft = get_draft(d)[:500]
        short_name = name[:50] + "..." if len(name) > 50 else name

        rows.append(f"""<tr>
<td><span class="tag tag-new">NEW</span> <small>{escape(short_name)}</small></td>
<td><b>{escape(exp)}</b></td>
<td class="{correct_class(corr)}">{escape(sc)}</td>
<td class="{correct_class(corr)}">{'[OK]' if corr else '[WRONG]'}</td>
<td>{fmt_sev(sev)}</td>
<td class="draft-cell" title="{escape(draft)}">{escape(draft[:120])}</td>
</tr>""")

    rows.append('</table>')
    return "\n".join(rows)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compare baseline vs new batch_test results")
    parser.add_argument("--baseline", default=str(RESULTS_ROOT / "baseline"),
                        help="Path to baseline results dir")
    parser.add_argument("--new", default=str(RESULTS_ROOT / "new"),
                        help="Path to new results dir")
    parser.add_argument("--output", default=str(RESULTS_ROOT / "comparison_report.html"),
                        help="Output HTML file path")
    parser.add_argument("--open", action="store_true",
                        help="Open the report in the default browser after generating")
    args = parser.parse_args()

    base_dir = Path(args.baseline)
    new_dir  = Path(args.new)
    out_path = Path(args.output)

    if not base_dir.exists():
        print(f"ERROR: baseline dir not found: {base_dir}", file=sys.stderr)
        sys.exit(1)
    if not new_dir.exists():
        print(f"ERROR: new dir not found: {new_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading baseline from: {base_dir}")
    baseline = load_dir(base_dir)
    print(f"  {len(baseline)} samples loaded")

    print(f"Loading new results from: {new_dir}")
    new = load_dir(new_dir)
    print(f"  {len(new)} samples loaded")

    base_stats = compute_stats(baseline)
    new_stats  = compute_stats(new)

    all_keys = sorted(set(list(baseline.keys()) + list(new.keys())))
    common   = sorted(set(baseline.keys()) & set(new.keys()))
    only_new = sorted(set(new.keys()) - set(baseline.keys()))
    only_base= sorted(set(baseline.keys()) - set(new.keys()))

    print(f"\nCommon samples: {len(common)}")
    print(f"Only in baseline: {len(only_base)}")
    print(f"Only in new: {len(only_new)}")

    print(f"\nBaseline accuracy: {base_stats['accuracy']}%  ({base_stats['correct']}/{base_stats['total']})")
    print(f"New accuracy:      {new_stats['accuracy']}%  ({new_stats['correct']}/{new_stats['total']})")
    print(f"S8 baseline: {base_stats['s8_count']}  ->  new: {new_stats['s8_count']}")

    improved  = [k for k in common if not is_correct(baseline[k]) and is_correct(new[k])]
    regressed = [k for k in common if is_correct(baseline[k]) and not is_correct(new[k])]
    print(f"Improved: {len(improved)}  Regressed: {len(regressed)}")

    html = generate_html(baseline, new, base_stats, new_stats, common, only_new, only_base)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\nReport written: {out_path}")

    if args.open:
        import webbrowser
        webbrowser.open(str(out_path))
        print("Opened in browser.")


if __name__ == "__main__":
    main()
