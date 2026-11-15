"""Offline end-to-end tests (mock LLM + fixture literature). Run: pytest -q"""
import json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from postudio.inputs import build_raw_materials
from postudio.pipeline import JobConfig, Pipeline
from postudio.literature import parse_bibtex, Paper, Registry, to_bibtex
from postudio.llm import parse_json, parse_latex


def _materials(tmp):
    form = json.load(open(os.path.join(ROOT, "examples/demo_forecasting/form.json")))
    build_raw_materials(form, str(tmp / "raw"), {})
    return str(tmp / "raw")


def test_parsers():
    assert parse_json('x ```json\n{"a": 1}\n``` y') == {"a": 1}
    assert parse_json('{"a": [1,2,],}') == {"a": [1, 2]}
    assert parse_latex("```latex\n\\documentclass{article}\n```").startswith("\\documentclass")


def test_bibtex_roundtrip():
    r = Registry()
    r.add(Paper(title="Long Short-Term Memory", authors=["Sepp Hochreiter", "Jürgen Schmidhuber"], year=1997,
                venue="Neural Computation", doi="10.1162/neco.1997.9.8.1735", volume="9", pages="1735--1780"))
    bib = r.bibtex()
    assert "Hochreiter1997LongShortterm" in bib and "doi" in bib
    back = parse_bibtex(bib)
    assert back[0].title == "Long Short-Term Memory" and back[0].year == 1997


def _run(tmp, template):
    cfg = JobConfig(template=template, writer_model="mock", reviewer_model="mock", offline_literature=True,
                    refine_rounds=1, authors=[{"name": "A. Author", "affiliation": "Uni", "corresponding": True}])
    st = Pipeline(_materials(tmp), str(tmp / "out"), cfg).run()
    assert st["state"] == "done"
    assert os.path.exists(tmp / "out/final/paper.pdf")
    assert os.path.exists(tmp / "out/submission_package.zip")
    # integrity check must flag fixture references
    assert any("TEST FIXTURE" in e for e in st["report"]["errors"])
    return st


def test_pipeline_generic(tmp_path):
    _run(tmp_path, "journal_generic")


def test_pipeline_vietnamese(tmp_path):
    _run(tmp_path, "journal_vi")


def test_pipeline_cvpr(tmp_path):
    _run(tmp_path, "cvpr2025")
