"""Research-integrity and submission-readiness checks for a generated manuscript."""
from __future__ import annotations

import json
import os
import re

CITE_RE = re.compile(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|parencite|textcite)\*?(?:\[[^\]]*\])*\{([^}]+)\}")
PLACEHOLDERS = ["Introduction here.", "Related work here.", "Methodology here.", "Conclusion here.",
                "Abstract here.", "Experimental setup, results, and analysis here.", "TODO", "XXX", "[citation needed]",
                "Lorem ipsum"]


def _strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)


def _bib_keys(bib: str) -> set:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib))


def _numbers(s: str) -> set:
    return {n.rstrip("0").rstrip(".") if "." in n else n
            for n in re.findall(r"(?<![\w.])-?\d+(?:[.,]\d+)?", s.replace("{,}", "."))}


def run_checks(tex_path: str, bib_path: str, materials_dir: str, figures_dir: str | None = None) -> dict:
    tex = _strip_comments(open(tex_path, encoding="utf-8").read())
    bib = open(bib_path, encoding="utf-8").read() if os.path.exists(bib_path) else ""
    log_path = os.path.join(materials_dir, "experimental_log.md")
    exp_log = open(log_path, encoding="utf-8").read() if os.path.exists(log_path) else ""
    ds_path = os.path.join(materials_dir, "data_summary.md")
    if os.path.exists(ds_path):
        exp_log += "\n" + open(ds_path, encoding="utf-8").read()

    report = {"errors": [], "warnings": [], "stats": {}}

    # 1. citations
    used = set()
    for grp in CITE_RE.findall(tex):
        used.update(k.strip() for k in grp.split(",") if k.strip())
    keys = _bib_keys(bib)
    missing = sorted(used - keys)
    if missing:
        report["errors"].append(f"Citation keys not in references.bib: {missing}")
    if "[TEST FIXTURE]" in bib:
        report["errors"].append("references.bib contains offline TEST FIXTURE entries — rerun literature search online.")
    report["stats"]["citations_used"] = len(used)
    report["stats"]["bib_entries"] = len(keys)
    report["stats"]["bib_entries_uncited"] = sorted(keys - used)

    # 2. numbers in tables must appear in the experimental log
    unmatched = []
    log_nums = _numbers(exp_log)
    for tab in re.findall(r"\\begin\{tabular\*?\}.*?\\end\{tabular\*?\}", tex, flags=re.DOTALL):
        body = re.sub(r"\\begin\{tabular\*?\}(\{[^}]*\})+", "", tab)
        for n in _numbers(body):
            if n.lstrip("-").isdigit() and len(n.lstrip("-")) <= 2:
                continue  # small integers (ranks, horizons, column counts)
            if n not in log_nums and n.lstrip("-") not in log_nums:
                unmatched.append(n)
    if unmatched:
        report["warnings"].append(
            f"{len(set(unmatched))} numeric values in tables were not found verbatim in experimental_log.md / "
            f"data_summary.md (check rounding or possible fabrication): {sorted(set(unmatched))[:30]}")
    report["stats"]["table_values_unmatched"] = sorted(set(unmatched))

    # 3. figures
    included = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex)
    base = os.path.dirname(tex_path)
    for f in included:
        cands = [os.path.join(base, f)] + [os.path.join(base, f + e) for e in (".png", ".pdf", ".jpg")]
        if not any(os.path.exists(c) for c in cands):
            report["errors"].append(f"Figure file not found: {f}")
    if figures_dir and os.path.isdir(figures_dir):
        avail = [x for x in os.listdir(figures_dir) if x.lower().endswith((".png", ".pdf", ".jpg", ".jpeg"))]
        unused = [x for x in avail if not any(x in i or os.path.splitext(x)[0] in i for i in included)]
        if unused:
            report["warnings"].append(f"Figures provided but not used: {unused}")
    report["stats"]["figures_included"] = len(included)

    # 4. labels / refs
    labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
    refs = set()
    for grp in re.findall(r"\\(?:ref|cref|Cref|autoref|eqref)\{([^}]+)\}", tex):
        refs.update(x.strip() for x in grp.split(","))
    if refs - labels:
        report["errors"].append(f"References to undefined labels: {sorted(refs - labels)}")
    unreferenced = [l for l in labels if (l.startswith(("fig", "tab")) and l not in refs)]
    if unreferenced:
        report["warnings"].append(f"Figures/tables never referenced in text: {sorted(unreferenced)}")

    # 5. placeholders & abstract length
    for ph in PLACEHOLDERS:
        if ph in tex:
            report["errors"].append(f"Template placeholder left in manuscript: '{ph}'")
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, flags=re.DOTALL)
    if m:
        words = len(re.sub(r"\\[a-zA-Z]+|[{}$]", " ", m.group(1)).split())
        report["stats"]["abstract_words"] = words
        if words > 300:
            report["warnings"].append(f"Abstract has {words} words (most journals allow 150-250).")
    body = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", tex.split("\\begin{document}")[-1])
    report["stats"]["approx_words"] = len(re.sub(r"[{}$\\]", " ", body).split())
    report["ok"] = not report["errors"]
    return report


def report_markdown(r: dict) -> str:
    lines = ["# Integrity & readiness report", "", f"**Status:** {'PASS' if r['ok'] else 'NEEDS ATTENTION'}", ""]
    if r["errors"]:
        lines += ["## Errors"] + [f"- {e}" for e in r["errors"]] + [""]
    if r["warnings"]:
        lines += ["## Warnings"] + [f"- {w}" for w in r["warnings"]] + [""]
    lines += ["## Stats", "```json", json.dumps({k: v for k, v in r["stats"].items()}, indent=2, ensure_ascii=False),
              "```"]
    return "\n".join(lines)
