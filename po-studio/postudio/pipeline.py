"""End-to-end orchestration of the PO-Studio pipeline.

    materials  ──► outline ──► (plots) ──► literature ──► sections ──► compile
               ──► review/refine loop ──► format check ──► integrity checks ──► package

Each stage writes its artefacts into ``out_dir`` and updates ``status.json`` so
that the web UI can show progress and a failed job can be resumed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import time
import traceback
import zipfile
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

from postudio import agents as A
from postudio.checks import report_markdown, run_checks
from postudio.latex import compile_latex, pdf_num_pages
from postudio.literature import LiteratureSearch
from postudio.llm import LLM, Usage
from postudio.prompts import WritingProfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.environ.get("POSTUDIO_TEMPLATES", os.path.join(ROOT, "templates"))

STAGES = ["prepare", "outline", "plotting", "literature", "sections", "compile", "refine", "format",
          "checks", "package"]


@dataclass
class JobConfig:
    template: str = "journal_generic"
    writer_model: str = "claude-sonnet-5-5"
    reviewer_model: str = "claude-sonnet-5-5"
    selector_model: str = ""                     # defaults to reviewer_model
    api_keys: dict = field(default_factory=dict)
    research_field: str = "the target research field"
    venue_name: str = ""
    language: str = ""                           # "" -> template default
    anonymous: Optional[bool] = None             # None -> template default
    cutoff: str = ""                             # YYYY-MM; default current month
    title: str = ""
    keywords: str = ""
    authors: list = field(default_factory=list)  # [{name, affiliation, email, corresponding}]
    declarations: dict = field(default_factory=dict)
    use_plotting: bool = True
    refine_rounds: int = 2
    review_ensemble: int = 1
    format_check: bool = True
    max_papers: int = 60
    mailto: str = ""
    s2_key: str = ""
    offline_literature: bool = False

    def public(self) -> dict:
        d = asdict(self)
        d["api_keys"] = {k: ("***" if v else "") for k, v in self.api_keys.items()}
        d["s2_key"] = "***" if self.s2_key else ""
        return d


def list_templates() -> dict:
    out = {}
    for name in sorted(os.listdir(TEMPLATES_DIR)):
        mp = os.path.join(TEMPLATES_DIR, name, "meta.json")
        if os.path.exists(mp):
            meta = json.load(open(mp, encoding="utf-8"))
            missing = [r for r in meta.get("requires", []) if not shutil.which("kpsewhich") or
                       os.popen(f"kpsewhich {r}").read().strip() == ""]
            meta["available"] = not missing
            meta["missing"] = missing
            out[name] = meta
    return out


# --------------------------------------------------------------------------
# Template preparation: title, authors, keywords, declarations
# --------------------------------------------------------------------------

def _tex_escape(s: str) -> str:
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                 ("_", r"\_"), ("{", r"\{"), ("}", r"\}")]:
        s = s.replace(a, b)
    return s


def format_authors(authors: list, style: str, anonymous: bool) -> str:
    if anonymous or not authors:
        if style == "elsarticle":
            return "\\author{Anonymous Author(s)}\n\\affiliation{organization={Anonymous Institution}}"
        if style == "ieee":
            return "\\author{Anonymous Author(s)}"
        return "\\author{Anonymous Author(s)}\n\\affil{Anonymous Institution}"
    affs = []
    for a in authors:
        aff = (a.get("affiliation") or "").strip()
        if aff and aff not in affs:
            affs.append(aff)
    lines = []
    if style == "elsarticle":
        for a in authors:
            idx = affs.index(a["affiliation"].strip()) + 1 if a.get("affiliation") else 1
            lines.append(f"\\author[{idx}]{{{_tex_escape(a['name'])}}}" + ("\\corref{cor1}" if a.get("corresponding") else ""))
            if a.get("email"):
                lines.append(f"\\ead{{{a['email']}}}")
        for i, aff in enumerate(affs, 1):
            lines.append(f"\\affiliation[{i}]{{organization={{{_tex_escape(aff)}}}}}")
        if any(a.get("corresponding") for a in authors):
            lines.append("\\cortext[cor1]{Corresponding author}")
        return "\n".join(lines)
    if style == "ieee":
        names = ", ".join(_tex_escape(a["name"]) for a in authors)
        notes = "; ".join(_tex_escape(a.get("affiliation", "")) + (f" (e-mail: {a['email']})" if a.get("email") else "")
                          for a in authors)
        return f"\\author{{{names}\\thanks{{{notes}}}}}"
    # authblk
    for a in authors:
        idx = affs.index(a["affiliation"].strip()) + 1 if a.get("affiliation") else 1
        star = "\\thanks{Corresponding author" + (f": {a['email']}" if a.get("email") else "") + "}" \
            if a.get("corresponding") else ""
        lines.append(f"\\author[{idx}]{{{_tex_escape(a['name'])}{star}}}")
    for i, aff in enumerate(affs, 1):
        lines.append(f"\\affil[{i}]{{{_tex_escape(aff)}}}")
    return "\n".join(lines)


DECL_FIELDS = [("funding", "Funding"), ("conflicts", "Conflict of interest"),
               ("data_availability", "Data availability"), ("ai_use", "Use of generative AI"),
               ("acknowledgements", "Acknowledgements")]
DECL_FIELDS_VI = {"Funding": "Tài trợ", "Conflict of interest": "Xung đột lợi ích",
                  "Data availability": "Tính sẵn có của dữ liệu", "Use of generative AI": "Sử dụng AI tạo sinh",
                  "Acknowledgements": "Lời cảm ơn"}


def format_declarations(decl: dict, anonymous: bool, lang: str, writer_model: str) -> str:
    if anonymous:
        return "Omitted for double-blind review." if lang != "vi" else "Được lược bỏ để phản biện kín."
    d = dict(decl or {})
    if not d.get("ai_use"):
        d["ai_use"] = (f"A draft of this manuscript was prepared with the assistance of an AI writing pipeline "
                       f"(PO-Studio, based on PaperOrchestra; language model: {writer_model}). The authors reviewed, "
                       f"verified and edited all content and take full responsibility for the publication."
                       if lang != "vi" else
                       f"Bản thảo được soạn với sự hỗ trợ của hệ thống viết bài dùng AI (PO-Studio, dựa trên "
                       f"PaperOrchestra; mô hình ngôn ngữ: {writer_model}). Tác giả đã rà soát, kiểm chứng, chỉnh sửa "
                       f"toàn bộ nội dung và chịu hoàn toàn trách nhiệm về bài báo.")
    out = []
    for k, label in DECL_FIELDS:
        v = (d.get(k) or "").strip()
        if not v and k == "acknowledgements":
            continue
        lab = DECL_FIELDS_VI[label] if lang == "vi" else label
        v = _tex_escape(v) if v else "\\textcolor{red}{[Author to complete]}"
        out.append(f"\\paragraph{{{lab}.}} {v}")
    return "\n".join(out)


def prepare_template(template_dir: str, dest: str, cfg: JobConfig, meta: dict, lang: str, anonymous: bool):
    shutil.copytree(template_dir, dest, dirs_exist_ok=True)
    tp = os.path.join(dest, "template.tex")
    tex = open(tp, encoding="utf-8").read()
    kw = [k.strip() for k in cfg.keywords.replace(";", ",").split(",") if k.strip()]
    repl = {
        "%%TITLE%%": _tex_escape(cfg.title) if cfg.title else "Title to be written",
        "%%AUTHORS%%": format_authors(cfg.authors, meta.get("author_style", "authblk"), anonymous),
        "%%KEYWORDS%%": "; ".join(_tex_escape(k) for k in kw) or "keywords to be written",
        "%%KEYWORDS_ELS%%": " \\sep ".join(_tex_escape(k) for k in kw) or "keywords to be written",
        "%%VENUE%%": _tex_escape(cfg.venue_name or "Journal"),
        "%%DECLARATIONS%%": format_declarations(cfg.declarations, anonymous, lang, cfg.writer_model),
    }
    for k, v in repl.items():
        tex = tex.replace(k, v)
    with open(tp, "w", encoding="utf-8") as f:
        f.write(tex)
    if not os.path.exists(os.path.join(dest, "references.bib")):
        open(os.path.join(dest, "references.bib"), "w").close()


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

class Pipeline:
    def __init__(self, materials_dir: str, out_dir: str, cfg: JobConfig,
                 on_event: Optional[Callable[[dict], None]] = None):
        self.materials_src = materials_dir
        self.out = os.path.abspath(out_dir)
        self.cfg = cfg
        self.on_event = on_event
        os.makedirs(self.out, exist_ok=True)
        self.status_path = os.path.join(self.out, "status.json")
        self.log_path = os.path.join(self.out, "pipeline.log")
        self.status = self._load_status()
        self.usage = Usage()

    # ---------------- status & logging ----------------
    def _load_status(self) -> dict:
        if os.path.exists(self.status_path):
            return json.load(open(self.status_path, encoding="utf-8"))
        return {"state": "queued", "stage": None, "stages": {s: "pending" for s in STAGES},
                "created": dt.datetime.now().isoformat(timespec="seconds"), "messages": []}

    def _save(self):
        self.status["usage"] = {"calls": self.usage.calls, "input_tokens": self.usage.input_tokens,
                                "output_tokens": self.usage.output_tokens, "by_agent": self.usage.by_agent}
        tmp = self.status_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.status, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.status_path)
        if self.on_event:
            self.on_event(self.status)

    def log(self, msg: str):
        line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.status["messages"] = (self.status.get("messages", []) + [line])[-200:]
        self._save()

    def _stage(self, name: str, state: str):
        self.status["stage"] = name
        self.status["stages"][name] = state
        self._save()

    def done(self, name: str) -> bool:
        return self.status["stages"].get(name) == "done"

    # ---------------- main ----------------
    def run(self, resume: bool = True) -> dict:
        cfg = self.cfg
        self.status["state"] = "running"
        self.status["config"] = cfg.public()
        self._save()
        try:
            return self._run(resume)
        except Exception as e:  # noqa: BLE001
            self.status["state"] = "failed"
            self.status["error"] = f"{type(e).__name__}: {e}"
            self.log("❌ FAILED: " + self.status["error"])
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            self._save()
            raise

    def _run(self, resume: bool) -> dict:
        cfg = self.cfg
        t0 = time.time()
        tdir = cfg.template if os.path.isdir(cfg.template) else os.path.join(TEMPLATES_DIR, cfg.template)
        meta = json.load(open(os.path.join(tdir, "meta.json"), encoding="utf-8")) \
            if os.path.exists(os.path.join(tdir, "meta.json")) else {}
        # fall back on the web/CLI form stored with the materials
        man_path = os.path.join(self.materials_src, "manifest.json")
        if os.path.exists(man_path):
            form = json.load(open(man_path, encoding="utf-8")).get("form", {})
            cfg.title = cfg.title or form.get("title", "")
            cfg.keywords = cfg.keywords or form.get("keywords", "")
            if cfg.research_field == "the target research field" and form.get("field"):
                cfg.research_field = form["field"]
            cfg.venue_name = cfg.venue_name or form.get("venue_name", "")
            cfg.authors = cfg.authors or form.get("authors", [])
            cfg.declarations = cfg.declarations or form.get("declarations", {})
        lang = cfg.language or meta.get("language", "en")
        anonymous = meta.get("anonymous", False) if cfg.anonymous is None else cfg.anonymous
        engine = meta.get("engine", "pdflatex")
        cutoff = cfg.cutoff or dt.date.today().strftime("%Y-%m")
        profile = WritingProfile(field=cfg.research_field, venue_type=meta.get("venue_type", "journal"),
                                 venue_name=cfg.venue_name, language=lang, anonymous=anonymous,
                                 citation_style=meta.get("citation_style", "numeric"), cutoff=cutoff)

        materials = os.path.join(self.out, "raw_materials")
        latex_dir = os.path.join(self.out, "latex")
        lit_dir = os.path.join(self.out, "literature")

        mk = lambda m: LLM(m, cfg.api_keys, usage=self.usage, log=self.log)  # noqa: E731
        ctx = A.Ctx(writer=mk(cfg.writer_model), reviewer=mk(cfg.reviewer_model),
                    selector=mk(cfg.selector_model or cfg.reviewer_model), profile=profile,
                    materials=materials, workdir=latex_dir, engine=engine, log=self.log)

        # 0. prepare
        if not (resume and self.done("prepare")):
            self._stage("prepare", "running")
            if os.path.abspath(self.materials_src) != os.path.abspath(materials):
                shutil.copytree(self.materials_src, materials, dirs_exist_ok=True)
            if os.path.exists(latex_dir):
                shutil.rmtree(latex_dir)
            prepare_template(tdir, latex_dir, cfg, meta, lang, anonymous)
            src_fig = os.path.join(materials, "figures")
            if os.path.isdir(src_fig):
                shutil.copytree(src_fig, os.path.join(latex_dir, "figures"), dirs_exist_ok=True)
            os.makedirs(os.path.join(latex_dir, "figures"), exist_ok=True)
            if not os.path.exists(os.path.join(latex_dir, "figures", "info.json")):
                A.write(os.path.join(latex_dir, "figures", "info.json"), "[]")
            self.log(f"📁 Template '{os.path.basename(tdir)}' ({engine}, {profile.citation_style}, "
                     f"lang={lang}, anonymous={anonymous}); literature cutoff {cutoff}")
            self._stage("prepare", "done")

        template_tex = A.read(os.path.join(latex_dir, "template.tex"))
        guidelines = A.read(os.path.join(latex_dir, "guidelines.md"))
        outline_path = os.path.join(self.out, "outline.json")

        # 1. outline
        if resume and self.done("outline"):
            outline = json.load(open(outline_path, encoding="utf-8"))
        else:
            self._stage("outline", "running")
            outline = A.run_outline(ctx, template_tex, guidelines, outline_path)
            if not cfg.title and outline.get("title_suggestion"):
                t = _tex_escape(outline["title_suggestion"])
                template_tex = template_tex.replace("Title to be written", t)
                A.write(os.path.join(latex_dir, "template.tex"), template_tex)
            self._stage("outline", "done")

        # 1b. plotting
        if not (resume and self.done("plotting")):
            if cfg.use_plotting and outline.get("plotting_plan"):
                self._stage("plotting", "running")
                A.run_plotting(ctx, outline)
            self._stage("plotting", "done")

        # 2-3. literature + intro/related work
        cmap_path = os.path.join(lit_dir, "citation_map.json")
        if resume and self.done("literature"):
            cmap = json.load(open(cmap_path, encoding="utf-8"))
            outline = json.load(open(os.path.join(lit_dir, "outline_v1.json"), encoding="utf-8"))
        else:
            self._stage("literature", "running")
            search = LiteratureSearch(cutoff=cutoff, mailto=cfg.mailto, s2_key=cfg.s2_key,
                                      offline=cfg.offline_literature, log=self.log)
            lit = A.run_literature(ctx, outline, template_tex, lit_dir, search, max_papers=cfg.max_papers)
            cmap, outline = lit["citation_map"], lit["outline"]
            shutil.copy(os.path.join(lit_dir, "references.bib"), os.path.join(latex_dir, "references.bib"))
            A.write(os.path.join(latex_dir, "template.tex"), lit["latex"])
            A.write(outline_path, json.dumps(outline, indent=2, ensure_ascii=False))
            self._stage("literature", "done")

        # 4. sections
        draft_path = os.path.join(latex_dir, "draft.tex")
        if resume and self.done("sections"):
            draft = A.read(draft_path)
        else:
            self._stage("sections", "running")
            draft = A.run_section_writer(ctx, outline, A.read(os.path.join(latex_dir, "template.tex")), cmap,
                                         guidelines)
            A.write(draft_path, draft)
            self._stage("sections", "done")

        # 5. compile
        self._stage("compile", "running")
        self.log("🛠️  Compiling draft …")
        draft, pdf = A.compile_with_repair(ctx, draft, "draft")
        if not pdf:
            raise RuntimeError("Draft could not be compiled; see latex/draft.log")
        self._stage("compile", "done")
        tex = draft

        # 6. refine
        if cfg.refine_rounds > 0 and not (resume and self.done("refine")):
            self._stage("refine", "running")
            tex, pdf, review = A.run_refinement(ctx, tex, pdf, cmap, guidelines, cfg.refine_rounds,
                                                cfg.review_ensemble)
            self.status["review"] = {k: review.get(k) for k in A.AXES + ["Decision", "Summary"]}
            self.status["review"]["Weaknesses"] = review.get("Weaknesses", [])[:8]
        self._stage("refine", "done")

        # 7. format
        if cfg.format_check and not (resume and self.done("format")):
            self._stage("format", "running")
            tex, pdf, _ = A.run_format(ctx, tex, pdf, guidelines)
        self._stage("format", "done")

        # 8. final compile + checks
        self._stage("checks", "running")
        final_dir = os.path.join(self.out, "final")
        if os.path.exists(final_dir):
            shutil.rmtree(final_dir)
        os.makedirs(final_dir)
        for item in os.listdir(latex_dir):
            src = os.path.join(latex_dir, item)
            if item == "figures":
                shutil.copytree(src, os.path.join(final_dir, "figures"),
                                ignore=shutil.ignore_patterns("*_code.py", "info.json"))
            elif item.endswith((".sty", ".cls", ".bst", ".tex")) and item not in (
                    "template.tex",) and not item.startswith(("draft", "refined_v", "formatted")):
                shutil.copy(src, final_dir)
        A.write(os.path.join(final_dir, "paper.tex"), tex)
        shutil.copy(os.path.join(latex_dir, "references.bib"), final_dir)
        res = compile_latex(final_dir, "paper", engine=engine)
        report = run_checks(os.path.join(final_dir, "paper.tex"), os.path.join(final_dir, "references.bib"),
                            materials, os.path.join(latex_dir, "figures"))
        report["compile"] = {"ok": res["ok"], "warnings": res["warnings"], "errors": res["errors"][:5]}
        if res["ok"]:
            report["stats"]["pages"] = pdf_num_pages(res["pdf"])
        A.write(os.path.join(self.out, "report.json"), json.dumps(report, indent=2, ensure_ascii=False))
        A.write(os.path.join(self.out, "report.md"), report_markdown(report))
        for f in os.listdir(final_dir):
            if f.startswith("paper.") and f.split(".")[-1] in ("aux", "log", "out", "blg", "bbl", "toc"):
                if f != "paper.bbl":
                    os.remove(os.path.join(final_dir, f))
        self.status["report"] = {"ok": report["ok"], "errors": report["errors"], "warnings": report["warnings"],
                                 "stats": {k: v for k, v in report["stats"].items() if not isinstance(v, list)}}
        self._stage("checks", "done")

        # 9. package
        self._stage("package", "running")
        zip_path = os.path.join(self.out, "submission_package.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for rootd, _, files in os.walk(final_dir):
                for f in files:
                    p = os.path.join(rootd, f)
                    z.write(p, os.path.relpath(p, final_dir))
            for extra in ("report.md", "outline.json"):
                if os.path.exists(os.path.join(self.out, extra)):
                    z.write(os.path.join(self.out, extra), f"_pipeline/{extra}")
            for extra in ("literature/citation_map.json", "peer_reviews/refinement_worklog.json"):
                p = os.path.join(self.out, extra)
                if os.path.exists(p):
                    z.write(p, f"_pipeline/{os.path.basename(extra)}")
        self._stage("package", "done")
        self.status["state"] = "done"
        self.status["outputs"] = {"pdf": "final/paper.pdf" if res["ok"] else None, "tex": "final/paper.tex",
                                  "zip": "submission_package.zip", "report": "report.md"}
        self.status["elapsed_sec"] = round(time.time() - t0, 1)
        self.log(f"🎉 Done in {self.status['elapsed_sec']}s — {self.usage.calls} LLM calls, "
                 f"{self.usage.input_tokens:,} in / {self.usage.output_tokens:,} out tokens")
        return self.status
