#!/usr/bin/env python3
"""Analyze Simplify failure patterns across feedback-loop iterations.

Walks `.research/simplify-loop/iterations/NNN/unresolved_fields.json` and
`result.json` for every passing iteration, classifies the unresolved
fields by type/label/required-ness, and emits a markdown summary plus a
per-iteration CSV so we can see which categories Simplify never autofills.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP_ROOT = REPO_ROOT / ".research" / "simplify-loop"
ITER_DIR = LOOP_ROOT / "iterations"
OUT_DIR = LOOP_ROOT / "analysis"


# Label-pattern → human-readable category.
# Order matters: first match wins. Regex is case-insensitive.
_LABEL_CATEGORIES: list[tuple[str, str]] = [
    (r"cover\s*letter", "cover_letter"),
    (r"why.*(interest|join|want|excit)", "freeform_motivation"),
    (r"(tell|describe|share).*(yourself|background|story)", "freeform_about_me"),
    (r"(salary|compensation|expected\s*pay|hourly)", "salary_expectation"),
    (r"how\s+did\s+you\s+(hear|find\s+out)", "referral_source"),
    (r"(referr|referee|refer\b)", "referral"),
    (r"(linkedin)", "linkedin_url"),
    (r"(github|portfolio|website|personal\s*site)", "portfolio_url"),
    (r"(visa|sponsorship|authoriz|right\s*to\s*work)", "work_authorization"),
    (r"(start\s*date|when\s*can\s*you\s*start|earliest|notice)", "start_date"),
    (r"(relocat|willing\s*to\s*move)", "relocation"),
    (r"(disability|gender|race|ethnic|veteran|age|pronoun|self\s*identif|EEO|equal\s*opportunit)", "demographics"),
    (r"location|address|city|state|country|zip|postal", "location"),
    (r"phone", "phone"),
    (r"email", "email"),
    (r"name(?!.*last)", "name_first"),
    (r"last\s*name|surname", "name_last"),
    (r"(school|university|college|institution|education|degree|major|gpa)", "education"),
    (r"(experience|years.*work|work.*history)", "experience"),
    (r"(file|upload|attach|cv|resume)", "file_upload"),
    (r"(remote|in.*office|on.*site|hybrid)", "work_mode"),
    (r"(citizen|nationality)", "citizenship"),
    (r"(security\s*clearance|clearance|background\s*check)", "security_clearance"),
    (r"(consent|agree|terms|policy|privacy)", "consent_checkbox"),
    (r"(pronouns)", "pronouns"),
    (r"acknowledge|certify|confirm", "acknowledgement_checkbox"),
]


def _category_for_label(label: str | None) -> str:
    if not label:
        return "no_label"
    text = label.strip().lower()
    for pattern, cat in _LABEL_CATEGORIES:
        if re.search(pattern, text):
            return cat
    return "other"


def _load_iter(iter_num: int) -> dict[str, Any] | None:
    """Load result.json + unresolved_fields.json for one iteration.

    Output:
        Dict with the merged data, or None if the iteration didn't finish.
    """

    iter_path = ITER_DIR / f"{iter_num:03d}"
    result_path = iter_path / "result.json"
    if not result_path.exists():
        return None
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    unresolved_path = iter_path / "unresolved_fields.json"
    unresolved: list[dict[str, Any]] = []
    if unresolved_path.exists():
        try:
            unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
        except Exception:
            unresolved = []

    return {
        "iter": iter_num,
        "target_url": result.get("target_url"),
        "pass": result.get("pass"),
        "apply_outcome": (result.get("apply_run_result") or {}).get("outcome"),
        "ats": _ats_from_url(result.get("target_url", "")),
        "unresolved_count": len(unresolved),
        "confidence": (
            (result.get("apply_run_result") or {}).get("confidence_report") or {}
        ).get("score"),
        "simplify_detected": (
            (result.get("apply_run_result") or {}).get("confidence_report") or {}
        ).get("simplify_autofill_detected"),
        "unresolved": unresolved,
    }


def _ats_from_url(url: str) -> str:
    """Classify ATS host from URL."""
    if "greenhouse" in url:
        return "greenhouse"
    if "ashbyhq" in url:
        return "ashby"
    if "lever.co" in url:
        return "lever"
    if "myworkdayjobs" in url:
        return "workday"
    if "icims" in url:
        return "icims"
    if "taleo" in url:
        return "taleo"
    return "other"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for iter_path in sorted(ITER_DIR.iterdir()):
        if not iter_path.is_dir():
            continue
        try:
            iter_num = int(iter_path.name)
        except ValueError:
            continue
        rec = _load_iter(iter_num)
        if rec is None:
            continue
        rows.append(rec)

    pass_rows = [r for r in rows if r.get("pass")]

    # Per-ATS pass rate
    ats_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "pass": 0, "unresolved_total": 0}
    )
    for r in rows:
        ats_stats[r["ats"]]["total"] += 1
        if r.get("pass"):
            ats_stats[r["ats"]]["pass"] += 1
            ats_stats[r["ats"]]["unresolved_total"] += r["unresolved_count"]

    # Category breakdown across all PASS iterations
    category_counts: Counter[str] = Counter()
    category_required: Counter[str] = Counter()
    category_field_types: dict[str, Counter[str]] = defaultdict(Counter)
    category_examples: dict[str, list[str]] = defaultdict(list)

    for r in pass_rows:
        for f in r["unresolved"]:
            label = f.get("label") or ""
            cat = _category_for_label(label)
            category_counts[cat] += 1
            if f.get("is_required"):
                category_required[cat] += 1
            ftype = f.get("field_type") or "?"
            category_field_types[cat][ftype] += 1
            if len(category_examples[cat]) < 3 and label:
                category_examples[cat].append(label.strip()[:100])

    # Field-type distribution
    type_counts: Counter[str] = Counter()
    for r in pass_rows:
        for f in r["unresolved"]:
            type_counts[f.get("field_type") or "?"] += 1

    lines = [
        "# Simplify Failure Analysis",
        "",
        f"Total iterations parsed: {len(rows)}",
        f"Passing iterations: {len(pass_rows)}",
        f"Total unresolved fields across passing iterations: "
        f"{sum(r['unresolved_count'] for r in pass_rows)}",
        "",
        "## Per-iteration summary",
        "",
        "| Iter | ATS | URL | Confidence | Simplify | Unresolved | Pass |",
        "|------|-----|-----|------------|----------|------------|------|",
    ]
    for r in rows:
        url = (r["target_url"] or "")
        host = url.split("://", 1)[-1].split("/", 1)[0] if url else "?"
        path = "/".join((url or "").split("/")[3:])[:50]
        lines.append(
            f"| {r['iter']:03d} | {r['ats']} | `{host}/...{path}` "
            f"| {r['confidence']} | "
            f"{'✓' if r['simplify_detected'] else '✗'} | "
            f"{r['unresolved_count']} | "
            f"{'✓' if r['pass'] else '✗'} |"
        )

    lines += [
        "",
        "## Per-ATS stats",
        "",
        "| ATS | Iterations | Passes | Avg unresolved (per pass) |",
        "|-----|-----------:|-------:|--------------------------:|",
    ]
    for ats, stats in sorted(ats_stats.items()):
        avg = (
            stats["unresolved_total"] / stats["pass"]
            if stats["pass"]
            else 0.0
        )
        lines.append(
            f"| {ats} | {stats['total']} | {stats['pass']} | {avg:.1f} |"
        )

    lines += [
        "",
        "## Category breakdown (passing iterations)",
        "",
        "Sorted by frequency. `required` is the count of required fields in "
        "that category that Simplify left empty; high required + high count "
        "= top priority to handle.",
        "",
        "| Category | Total | Required | Field types | Sample labels |",
        "|----------|------:|---------:|-------------|---------------|",
    ]
    for cat, count in category_counts.most_common():
        ftypes = ", ".join(
            f"{ft}({n})"
            for ft, n in category_field_types[cat].most_common()
        )
        examples = " · ".join(category_examples[cat])
        lines.append(
            f"| {cat} | {count} | {category_required[cat]} | {ftypes} | {examples} |"
        )

    lines += [
        "",
        "## Field-type distribution",
        "",
        "| Type | Count |",
        "|------|------:|",
    ]
    for ftype, count in type_counts.most_common():
        lines.append(f"| {ftype} | {count} |")

    out_path = OUT_DIR / "failure_analysis.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Per-iteration CSV with classified unresolved fields
    csv_path = OUT_DIR / "unresolved_fields.csv"
    csv_lines = ["iter,ats,url,category,field_type,is_required,label"]
    for r in pass_rows:
        for f in r["unresolved"]:
            label = (f.get("label") or "").replace("\n", " ").replace(",", ";")[:200]
            cat = _category_for_label(f.get("label"))
            ftype = f.get("field_type") or "?"
            req = "1" if f.get("is_required") else "0"
            csv_lines.append(
                f"{r['iter']},{r['ats']},{r['target_url']},{cat},{ftype},{req},\"{label}\""
            )
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Wrote {csv_path}")
    print(f"\nIterations parsed: {len(rows)}")
    print(f"Passing: {len(pass_rows)}")
    print(f"Per-ATS: {dict(ats_stats)}")
    print("\nTop categories of unresolved fields:")
    for cat, count in category_counts.most_common(10):
        print(f"  {cat}: {count} (required: {category_required[cat]})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
