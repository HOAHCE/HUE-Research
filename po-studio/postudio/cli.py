"""Command-line interface.

Examples
--------
# Full pipeline from a raw_materials folder (idea.md + experimental_log.md [+ figures/])
postudio run --materials examples/btc_forecasting/raw_materials --template journal_generic \
             --field "financial time-series forecasting" --out runs/btc1

# Build raw_materials from a JSON form (same schema as the web form)
postudio materials --form form.json --out runs/btc1/raw_materials --data data.csv --results results.csv

# Stand-alone tools (used by the Claude skill as well)
postudio lit-search "LSTM bitcoin price forecasting" --cutoff 2025-06 -n 10
postudio verify-bib references.bib
postudio compile final/paper.tex --engine pdflatex
postudio check final/paper.tex --bib final/references.bib --materials raw_materials
postudio templates
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _cfg_from_args(a) -> "JobConfig":
    from postudio.pipeline import JobConfig
    authors = json.load(open(a.authors, encoding="utf-8")) if a.authors else []
    return JobConfig(template=a.template, writer_model=a.writer_model, reviewer_model=a.reviewer_model,
                     selector_model=a.selector_model or "", research_field=a.field, venue_name=a.venue, language=a.language,
                     anonymous=None if a.anonymous is None else a.anonymous == "true", cutoff=a.cutoff,
                     title=a.title, keywords=a.keywords, authors=authors, use_plotting=not a.no_plotting,
                     refine_rounds=a.refine_rounds, review_ensemble=a.review_ensemble,
                     format_check=not a.no_format_check, max_papers=a.max_papers, mailto=a.mailto,
                     offline_literature=a.offline)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="postudio", description="PO-Studio: automated paper writing (PaperOrchestra-based)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the full pipeline")
    r.add_argument("--materials", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--template", default="journal_generic")
    r.add_argument("--writer-model", default=os.environ.get("POSTUDIO_WRITER", "claude-sonnet-5-5"))
    r.add_argument("--reviewer-model", default=os.environ.get("POSTUDIO_REVIEWER", "claude-sonnet-5-5"))
    r.add_argument("--selector-model", default="")
    r.add_argument("--field", default="the target research field")
    r.add_argument("--venue", default="")
    r.add_argument("--language", default="", choices=["", "en", "vi"])
    r.add_argument("--anonymous", default=None, choices=["true", "false"])
    r.add_argument("--cutoff", default="")
    r.add_argument("--title", default="")
    r.add_argument("--keywords", default="")
    r.add_argument("--authors", default="", help="JSON file: [{name, affiliation, email, corresponding}]")
    r.add_argument("--no-plotting", action="store_true")
    r.add_argument("--refine-rounds", type=int, default=2)
    r.add_argument("--review-ensemble", type=int, default=1)
    r.add_argument("--no-format-check", action="store_true")
    r.add_argument("--max-papers", type=int, default=60)
    r.add_argument("--mailto", default=os.environ.get("OPENALEX_MAILTO", ""))
    r.add_argument("--offline", action="store_true", help="use fixture literature (tests only)")
    r.add_argument("--fresh", action="store_true", help="ignore previous progress in --out")

    m = sub.add_parser("materials", help="build raw_materials from a JSON form + files")
    m.add_argument("--form", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--data", nargs="*", default=[])
    m.add_argument("--results", nargs="*", default=[])
    m.add_argument("--figures", nargs="*", default=[], help="path or path::caption")
    m.add_argument("--references", nargs="*", default=[])
    m.add_argument("--notes", nargs="*", default=[])

    ls = sub.add_parser("lit-search", help="search OpenAlex/S2 (verified records only)")
    ls.add_argument("query")
    ls.add_argument("--cutoff", default="")
    ls.add_argument("-n", type=int, default=10)
    ls.add_argument("--bib", action="store_true", help="print BibTeX instead of a table")

    vb = sub.add_parser("verify-bib", help="check every BibTeX entry against OpenAlex (title match / DOI)")
    vb.add_argument("bib")

    c = sub.add_parser("compile", help="compile a .tex (engine + bibtex)")
    c.add_argument("tex")
    c.add_argument("--engine", default="pdflatex")

    ck = sub.add_parser("check", help="integrity checks on a manuscript")
    ck.add_argument("tex")
    ck.add_argument("--bib", required=True)
    ck.add_argument("--materials", required=True)
    ck.add_argument("--figures", default=None)

    sub.add_parser("templates", help="list templates")

    a = ap.parse_args(argv)

    if a.cmd == "run":
        from postudio.pipeline import Pipeline
        if a.fresh and os.path.exists(os.path.join(a.out, "status.json")):
            os.remove(os.path.join(a.out, "status.json"))
        st = Pipeline(a.materials, a.out, _cfg_from_args(a)).run()
        print(json.dumps({k: st.get(k) for k in ("state", "outputs", "report", "elapsed_sec")}, indent=2,
                         ensure_ascii=False))
    elif a.cmd == "materials":
        from postudio.inputs import build_raw_materials
        figs = [tuple(f.split("::", 1)) if "::" in f else (f, "") for f in a.figures]
        man = build_raw_materials(json.load(open(a.form, encoding="utf-8")), a.out,
                                  {"data": a.data, "results": a.results, "figures": figs,
                                   "references": a.references, "notes": a.notes})
        print(json.dumps(man, indent=2, ensure_ascii=False))
    elif a.cmd == "lit-search":
        from postudio.literature import LiteratureSearch, Registry
        res = LiteratureSearch(cutoff=a.cutoff).search(a.query, a.n)
        if a.bib:
            reg = Registry()
            for p in res:
                reg.add(p)
            print(reg.bibtex())
        else:
            for i, p in enumerate(res):
                print(f"[{i}] {p.title} ({p.year}) — {p.venue} | cited {p.citation_count} | doi:{p.doi}")
    elif a.cmd == "verify-bib":
        from postudio.literature import LiteratureSearch, parse_bibtex
        from thefuzz import fuzz
        s = LiteratureSearch()
        bad = 0
        for p in parse_bibtex(open(a.bib, encoding="utf-8").read()):
            hits = s.openalex(p.title, 3)
            best = max((fuzz.ratio(p.title.lower(), h.title.lower()) for h in hits), default=0)
            ok = best >= 85
            bad += not ok
            print(f"{'OK ' if ok else '???'} {best:3d}  {p.citation_key}: {p.title[:80]}")
        sys.exit(1 if bad else 0)
    elif a.cmd == "compile":
        from postudio.latex import compile_latex
        d, f = os.path.split(os.path.abspath(a.tex))
        res = compile_latex(d, os.path.splitext(f)[0], engine=a.engine)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["ok"] else 1)
    elif a.cmd == "check":
        from postudio.checks import report_markdown, run_checks
        print(report_markdown(run_checks(a.tex, a.bib, a.materials, a.figures)))
    elif a.cmd == "templates":
        from postudio.pipeline import list_templates
        for k, v in list_templates().items():
            print(f"{k:18s} {'✓' if v['available'] else '✗ needs ' + ','.join(v['missing'])}  {v['name']}")


if __name__ == "__main__":
    main()
