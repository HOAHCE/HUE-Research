"""Turn structured user input (web form / JSON) + uploaded files into the
paper-orchestra "raw materials" layout:

raw_materials/
  idea.md                 problem, questions, method, contributions
  experimental_log.md     setup + results (tables copied verbatim)
  data_summary.md         automatic profile of uploaded datasets (optional)
  notes.md                extra notes extracted from uploaded txt/md/pdf (optional)
  user_references.bib     user's own references (optional, must be cited)
  figures/                user figures + info.json [{name, caption}]
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Optional

IDEA_FIELDS = [
    ("title", "Working title"),
    ("field", "Research field"),
    ("keywords", "Keywords"),
    ("problem", "Problem statement & motivation"),
    ("research_questions", "Research questions / hypotheses"),
    ("contributions", "Intended contributions"),
    ("method", "Proposed methodology"),
    ("data_description", "Data description"),
    ("related_notes", "Notes on related work / known baselines"),
]
LOG_FIELDS = [
    ("experimental_setup", "Experimental setup (splits, hyper-parameters, hardware, software)"),
    ("results", "Results (tables, metrics, statistical tests)"),
    ("ablations", "Ablation / robustness / sensitivity analyses"),
    ("discussion_notes", "Author's interpretation & discussion notes"),
    ("limitations", "Known limitations"),
]


def _section(title: str, body: str) -> str:
    body = (body or "").strip()
    return f"## {title}\n{body}\n\n" if body else ""


def table_file_to_markdown(path: str, max_rows: int = 200) -> str:
    """Copy a CSV/XLSX results table to Markdown WITHOUT changing any value (read as strings)."""
    import pandas as pd
    if path.lower().endswith((".xlsx", ".xls")):
        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    else:
        sheets = {"": pd.read_csv(path, dtype=str, sep=None, engine="python")}
    out = []
    for name, df in sheets.items():
        df = df.fillna("")
        title = os.path.basename(path) + (f" — sheet '{name}'" if name else "")
        out.append(f"### Table from {title}\n")
        if len(df) > max_rows:
            out.append(f"(first {max_rows} of {len(df)} rows)\n")
            df = df.head(max_rows)
        out.append(df.to_markdown(index=False) + "\n")
    return "\n".join(out)


def profile_dataset(path: str) -> str:
    import pandas as pd
    try:
        if path.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(path)
        elif path.lower().endswith(".parquet"):
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, sep=None, engine="python")
    except Exception as e:  # noqa: BLE001
        return f"### {os.path.basename(path)}\nCould not be read automatically: {e}\n"
    lines = [f"### Dataset `{os.path.basename(path)}`",
             f"- Observations: {len(df)}; variables: {df.shape[1]}"]
    for c in df.columns:
        if df[c].dtype == object:
            try:
                d = pd.to_datetime(df[c], errors="raise")
                lines.append(f"- Date column `{c}`: {d.min().date()} to {d.max().date()} "
                             f"({d.nunique()} unique dates)")
            except Exception:  # noqa: BLE001
                pass
    miss = df.isna().sum()
    miss = miss[miss > 0]
    if len(miss):
        lines.append("- Missing values: " + ", ".join(f"{k}={v}" for k, v in miss.items()))
    num = df.select_dtypes("number")
    if not num.empty:
        desc = num.describe().T[["count", "mean", "std", "min", "max"]].round(4)
        lines.append("\nDescriptive statistics (computed automatically):\n")
        lines.append(desc.to_markdown())
    return "\n".join(lines) + "\n"


def extract_text(path: str) -> str:
    if path.lower().endswith(".pdf"):
        import pymupdf
        return "\n".join(p.get_text() for p in pymupdf.open(path))[:60000]
    if path.lower().endswith(".docx"):
        try:
            import docx  # python-docx
            return "\n".join(p.text for p in docx.Document(path).paragraphs)
        except Exception:  # noqa: BLE001
            return ""
    return open(path, encoding="utf-8", errors="replace").read()[:60000]


def build_raw_materials(form: dict, out_dir: str, files: Optional[dict] = None) -> dict:
    """Create raw_materials/ from a form dict and uploaded file paths.

    files = {"data": [paths], "results": [paths], "figures": [(path, caption)],
             "references": [paths], "notes": [paths]}
    Returns a manifest dict.
    """
    files = files or {}
    os.makedirs(out_dir, exist_ok=True)
    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    idea = "# Research idea\n\n" + "".join(_section(t, form.get(k, "")) for k, t in IDEA_FIELDS)
    log = "# Experimental log\n\n" + "".join(_section(t, form.get(k, "")) for k, t in LOG_FIELDS)
    for p in files.get("results", []):
        if p.lower().endswith((".csv", ".tsv", ".xlsx", ".xls")):
            log += table_file_to_markdown(p) + "\n"
        else:
            log += f"### From {os.path.basename(p)}\n" + extract_text(p) + "\n\n"
    with open(os.path.join(out_dir, "idea.md"), "w", encoding="utf-8") as f:
        f.write(idea)
    with open(os.path.join(out_dir, "experimental_log.md"), "w", encoding="utf-8") as f:
        f.write(log)

    if files.get("data"):
        summ = "# Data summary (auto-generated)\n\n" + "\n".join(profile_dataset(p) for p in files["data"])
        with open(os.path.join(out_dir, "data_summary.md"), "w", encoding="utf-8") as f:
            f.write(summ)

    if files.get("notes"):
        notes = "# Additional author notes\n\n" + "\n\n".join(
            f"## {os.path.basename(p)}\n{extract_text(p)}" for p in files["notes"])
        with open(os.path.join(out_dir, "notes.md"), "w", encoding="utf-8") as f:
            f.write(notes)

    info = []
    for item in files.get("figures", []):
        path, caption = item if isinstance(item, (list, tuple)) else (item, "")
        name = os.path.basename(path).replace(" ", "_")
        shutil.copy(path, os.path.join(fig_dir, name))
        info.append({"name": name, "caption": caption or ""})
    with open(os.path.join(fig_dir, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    if files.get("references"):
        with open(os.path.join(out_dir, "user_references.bib"), "w", encoding="utf-8") as f:
            for p in files["references"]:
                f.write(open(p, encoding="utf-8", errors="replace").read() + "\n")

    manifest = {"form": {k: v for k, v in form.items() if k not in ("api_key",)},
                "figures": info,
                "files": {k: [os.path.basename(x if isinstance(x, str) else x[0]) for x in v] for k, v in files.items()}}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest
