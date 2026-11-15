"""The PO-Studio agent team (port of paper-orchestra methods/agents/*).

Outline -> (Plotting) -> Literature review -> Section writing -> Compile/fix
-> Content refinement (review loop with accept/revert) -> Format refinement.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Optional

from postudio import prompts as P
from postudio.latex import compile_latex, pdf_text, pdf_to_grid_images
from postudio.literature import LiteratureSearch, Paper, Registry, parse_bibtex
from postudio.llm import LLM, parse_json, parse_json_and_latex, parse_latex, parse_python


def read(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return default


def write(path: str, text: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@dataclass
class Ctx:
    writer: LLM
    reviewer: LLM
    selector: LLM
    profile: P.WritingProfile
    materials: str                    # raw_materials dir
    workdir: str                      # latex working dir (template copy)
    engine: str = "pdflatex"
    log: Callable[[str], None] = print

    def material(self, name: str) -> str:
        return read(os.path.join(self.materials, name))

    @property
    def figures_dir(self) -> str:
        return os.path.join(self.workdir, "figures")

    def figures_info(self) -> list:
        try:
            return json.load(open(os.path.join(self.figures_dir, "info.json"), encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []

    def materials_bundle(self) -> str:
        parts = [f"--- idea.md ---\n{self.material('idea.md')}",
                 f"--- experimental_log.md ---\n{self.material('experimental_log.md')}"]
        for extra in ("data_summary.md", "notes.md"):
            t = self.material(extra)
            if t:
                parts.append(f"--- {extra} ---\n{t}")
        return "\n\n".join(parts)


# =============================================================================
# 1. Outline
# =============================================================================

def run_outline(ctx: Ctx, template_tex: str, guidelines: str, out_path: str) -> dict:
    ctx.log("🧭 [1/6] Outline agent: planning structure, figures and literature search …")
    figs = ctx.figures_info()
    prompt = (ctx.materials_bundle()
              + f"\n\n--- template.tex ---\n{template_tex}\n\n--- guidelines.md ---\n{guidelines}"
              + f"\n\n--- figures_list (already provided by the author) ---\n{json.dumps(figs, ensure_ascii=False)}")
    outline = ctx.writer.generate(prompt, system=P.outline_prompt(ctx.profile), temperature=0.4,
                                  agent="outline", parser=parse_json)
    for k in ("plotting_plan", "intro_related_work_plan", "section_plan"):
        outline.setdefault(k, [] if k != "intro_related_work_plan" else {})
    write(out_path, json.dumps(outline, indent=2, ensure_ascii=False))
    n_rw = len(outline["intro_related_work_plan"].get("related_work_strategy", {}).get("subsections", []))
    ctx.log(f"   → {len(outline['section_plan'])} planned sections, {n_rw} related-work clusters, "
            f"{len(outline['plotting_plan'])} planned figures")
    return outline


# =============================================================================
# 2. Plotting (matplotlib code generation + vision critic)
# =============================================================================

def _run_plot_code(code: str, out_png: str, timeout: int = 90) -> tuple[bool, str]:
    script = f"OUTPUT_PATH = {out_png!r}\nimport matplotlib\nmatplotlib.use('Agg')\n" + code
    path = out_png.replace(".png", "_code.py")
    write(path, script)
    try:
        r = subprocess.run([sys.executable, "-I", path], capture_output=True, text=True, timeout=timeout,
                           cwd=os.path.dirname(out_png))
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if "INSUFFICIENT_DATA" in r.stdout:
        return False, "INSUFFICIENT_DATA"
    return os.path.exists(out_png), (r.stderr or r.stdout)[-3000:]


def run_plotting(ctx: Ctx, outline: dict, max_rounds: int = 2) -> list:
    plan = outline.get("plotting_plan") or []
    if not plan:
        return []
    ctx.log(f"📊 [1b] Plotting agent: generating {len(plan)} figure(s) from the logged data …")
    os.makedirs(ctx.figures_dir, exist_ok=True)
    info = ctx.figures_info()
    done = []

    def one(fig):
        fid = re.sub(r"[^a-zA-Z0-9_]", "_", fig.get("figure_id", "fig"))
        out_png = os.path.join(ctx.figures_dir, f"{fid}.png")
        spec = json.dumps(fig, ensure_ascii=False, indent=1)
        prompt = f"FIGURE SPECIFICATION:\n{spec}\n\nSOURCE MATERIALS:\n{ctx.materials_bundle()}"
        feedback = ""
        caption = fig.get("title", "")
        for rnd in range(max_rounds):
            code = ctx.writer.generate(prompt + feedback, system=P.plotting_prompt(ctx.profile),
                                       temperature=0.3, agent="plotting", parser=parse_python)
            ok, msg = _run_plot_code(code, out_png)
            if msg == "INSUFFICIENT_DATA":
                ctx.log(f"   ⏭️  {fid}: insufficient data in materials, skipped")
                return None
            if not ok:
                feedback = f"\n\nThe previous script failed with:\n{msg}\nFix it."
                continue
            crit = ctx.reviewer.generate(P.PLOT_CRITIC_PROMPT.replace("{spec}", spec)
                                         + "\nSOURCE DATA:\n" + ctx.material("experimental_log.md")[:20000],
                                         attachments=[out_png], temperature=0.2, agent="plot_critic",
                                         parser=parse_json)
            caption = crit.get("caption") or caption
            if crit.get("acceptable", True) or rnd == max_rounds - 1:
                ctx.log(f"   ✅ {fid}.png")
                return {"name": f"{fid}.png", "caption": caption, "generated": True}
            feedback = "\n\nReviewer issues with the previous figure:\n- " + "\n- ".join(crit.get("issues", []))
        if os.path.exists(out_png):
            return {"name": f"{fid}.png", "caption": caption, "generated": True}
        ctx.log(f"   ❌ {fid}: could not be generated")
        return None

    with ThreadPoolExecutor(max_workers=3) as ex:
        for r in ex.map(one, plan):
            if r:
                done.append(r)
    info.extend(done)
    write(os.path.join(ctx.figures_dir, "info.json"), json.dumps(info, indent=2, ensure_ascii=False))
    return done


# =============================================================================
# 3. Literature review
# =============================================================================

_HINT_PREFIX = re.compile(r"^(research paper|paper|technical report|research paper or technical report)\s+"
                          r"(or technical report\s+)?introducing\s+", re.I)


def collect_search_tasks(outline: dict) -> list:
    tasks = []
    plan = outline.get("intro_related_work_plan", {})
    intro = plan.get("introduction_strategy", {})
    for d in intro.get("search_directions", []):
        tasks.append({"section": "Introduction", "focus": d, "type": "exploration",
                      "context": f"Hook: {intro.get('hook_hypothesis', '')}. Gap: {intro.get('problem_gap_hypothesis', '')}"})
    for sub in plan.get("related_work_strategy", {}).get("subsections", []):
        qs = sub.get("limitation_search_queries") or [f"{sub.get('subsection_title', '')} {sub.get('methodology_cluster', '')}"]
        for q in qs + [sub.get("methodology_cluster", "")]:
            if q:
                tasks.append({"section": f"Related Work: {sub.get('subsection_title', 'General')}", "focus": q,
                              "type": "exploration",
                              "context": f"Mission: {sub.get('sota_investigation_mission', '')}. "
                                         f"Hypothesis: {sub.get('limitation_hypothesis', '')}"})
    for sec in outline.get("section_plan", []):
        for sub in sec.get("subsections", []):
            for h in sub.get("citation_hints", []):
                tasks.append({"section": f"{sec.get('section_title', '')} - {sub.get('subsection_title', '')}",
                              "focus": h, "type": "targeted",
                              "context": "Must-have citation for: " + " ".join(sub.get("content_bullets", []))})
    return tasks


def _hint_to_query(h: str) -> str:
    h = _HINT_PREFIX.sub("", h.strip()).strip("'\" ")
    m = re.match(r"^[^()]+\((.+)\)$", h)  # "Author (Exact Title)" -> title
    return m.group(1) if m else h


def run_literature(ctx: Ctx, outline: dict, template_tex: str, out_dir: str,
                   search: LiteratureSearch, max_papers: int = 60, workers: int = 4) -> dict:
    ctx.log("📚 [2/6] Literature agent: searching OpenAlex/Semantic Scholar and selecting verified papers …")
    os.makedirs(out_dir, exist_ok=True)
    reg = Registry()
    user_bib = os.path.join(ctx.materials, "user_references.bib")
    if os.path.exists(user_bib):
        for p in parse_bibtex(read(user_bib)):
            reg.add(p)
        ctx.log(f"   → {len(reg.papers)} user-provided references loaded")

    tasks = collect_search_tasks(outline)
    ctx.log(f"   → {len(tasks)} search tasks")
    selector_sys = P.candidate_selection_prompt(ctx.profile)

    def do(task):
        q = _hint_to_query(task["focus"]) if task["type"] == "targeted" else task["focus"]
        cands = search.search(q, n=10 if task["type"] == "targeted" else 15)
        if not cands:
            try:
                qs = ctx.selector.generate(f"SEARCH TASK ({task['type']}): {task['focus']}\nCONTEXT: {task['context']}",
                                           system=P.query_expansion_prompt(ctx.profile), temperature=0.2,
                                           agent="lit_query", parser=parse_json).get("queries", [])
            except Exception:  # noqa: BLE001
                qs = []
            for q2 in qs[:3]:
                cands += search.search(q2, n=10)
        if not cands:
            return task, []
        listing = "\n".join(
            f"[{i}] {c.title} ({c.year}; {c.venue or 'n/a'}; cited {c.citation_count})\n    {c.abstract[:350]}"
            for i, c in enumerate(cands))
        sel = ctx.selector.generate(
            f"SEARCH TASK ({task['type']}): {task['focus']}\nSECTION: {task['section']}\nCONTEXT: {task['context']}"
            f"\n\nCANDIDATES:\n{listing}", system=selector_sys, temperature=0.1, agent="lit_select",
            parser=parse_json)
        chosen = []
        for s in (sel.get("selected", []) if isinstance(sel, dict) else []):
            try:
                c = cands[int(s["index"])]
            except Exception:  # noqa: BLE001
                continue
            if not c.abstract:
                continue
            c.found_in_section, c.reason = task["section"], s.get("reason", "")
            chosen.append(c)
        return task, chosen[:1] if task["type"] == "targeted" else chosen

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(do, t) for t in tasks]
        for f in as_completed(futs):
            try:
                task, chosen = f.result()
            except Exception as e:  # noqa: BLE001
                ctx.log(f"   ⚠️ search task failed: {e}")
                continue
            for c in chosen:
                if len(reg.papers) < max_papers and reg.add(c):
                    ctx.log(f"   + {c.citation_key}: {c.title[:90]}")

    ctx.log(f"   → {len(reg.papers)} verified references in library")
    bib = reg.bibtex()
    cmap = reg.citation_map()
    write(os.path.join(out_dir, "references.bib"), bib)
    write(os.path.join(out_dir, "citation_map.json"), json.dumps(cmap, indent=2, ensure_ascii=False))
    reg.dump(os.path.join(out_dir, "papers_full.json"))

    # inject citation candidates back into the outline (as in paper-orchestra)
    by_sec = {}
    for p in reg.papers.values():
        by_sec.setdefault(p.found_in_section, []).append(p.citation_key)
    plan = outline.get("intro_related_work_plan", {})
    plan.get("introduction_strategy", {})["citation_candidates"] = by_sec.get("Introduction", []) + \
        by_sec.get("User-provided references", [])
    for sub in plan.get("related_work_strategy", {}).get("subsections", []):
        sub["citation_candidates"] = by_sec.get(f"Related Work: {sub.get('subsection_title', 'General')}", [])
    for sec in outline.get("section_plan", []):
        for sub in sec.get("subsections", []):
            sub["citation_candidates"] = by_sec.get(f"{sec.get('section_title', '')} - {sub.get('subsection_title', '')}", [])
            sub.pop("citation_hints", None)
    write(os.path.join(out_dir, "outline_v1.json"), json.dumps(outline, indent=2, ensure_ascii=False))

    # write Introduction + Related Work
    ctx.log("✍️  [3/6] Writing Introduction and Related Work …")
    papers = list(cmap.values())
    payload = {
        "template.tex": template_tex,
        "intro_related_work_plan": outline.get("intro_related_work_plan", {}),
        "project_idea": ctx.material("idea.md"),
        "project_experimental_log": ctx.material("experimental_log.md"),
        "citation_checklist": [p["citation_key"] for p in papers],
        "collected_papers": [{k: p[k] for k in ("citation_key", "title", "authors", "venue", "year", "abstract",
                                                 "found_in_section")} for p in papers],
    }
    latex = ctx.writer.generate(
        "Generate the LaTeX for the Introduction and Related Work sections.\n\n" + json.dumps(payload, ensure_ascii=False),
        system=P.literature_writer_prompt(ctx.profile, len(papers), int(len(papers) * 0.9)),
        temperature=0.6, agent="lit_writer", parser=parse_latex)
    write(os.path.join(out_dir, "updated_template.tex"), latex)
    return {"latex": latex, "bib": bib, "citation_map": cmap, "outline": outline}


# =============================================================================
# 4. Section writing
# =============================================================================

def citation_library_text(cmap: dict) -> str:
    out = ["### REFERENCE LIBRARY (use these keys only)"]
    for k, d in cmap.items():
        a = ", ".join(d.get("authors", [])[:3]) + (" et al." if len(d.get("authors", [])) > 3 else "")
        out.append(f"--- Key: {k} ---\nTitle: {d['title']}\nAuthors: {a} ({d.get('year')})\nAbstract: {d.get('abstract', '')}\n")
    return "\n".join(out)


def run_section_writer(ctx: Ctx, outline: dict, template_tex: str, cmap: dict, guidelines: str) -> str:
    ctx.log("✍️  [4/6] Section writing agent: method, experiments, tables, figures, conclusion …")
    figs = ctx.figures_info()
    fig_txt = "\n".join(f"Item {i + 1}: Filename: {f['name']} | Caption: {f.get('caption', '')}"
                        for i, f in enumerate(figs)) or "No figures provided."
    images = [os.path.join(ctx.figures_dir, f["name"]) for f in figs
              if f["name"].lower().endswith((".png", ".jpg", ".jpeg"))
              and os.path.exists(os.path.join(ctx.figures_dir, f["name"]))]
    prompt = f"""--- INPUT: outline.json ---
{json.dumps(outline, indent=1, ensure_ascii=False)}

--- INPUT: citation library ---
{citation_library_text(cmap)}

{ctx.materials_bundle()}

--- INPUT: figures_list (images attached in the same order) ---
{fig_txt}

--- INPUT: guidelines.md ---
{guidelines}

--- INPUT: template.tex (DO NOT CHANGE EXISTING TEXT. FILL MISSING SECTIONS.) ---
{template_tex}

INSTRUCTION: identify the empty sections, write them following outline.json, build tables from
experimental_log.md, include every figure, cite only library keys, and return the full compilable LaTeX file."""
    return ctx.writer.generate(prompt, system=P.section_writer_prompt(ctx.profile), attachments=images[:20],
                               temperature=0.7, agent="section_writer", parser=parse_latex)


# =============================================================================
# 5. Compile with automatic repair
# =============================================================================

def compile_with_repair(ctx: Ctx, tex: str, name: str, max_fixes: int = 2) -> tuple[str, Optional[str]]:
    for attempt in range(max_fixes + 1):
        write(os.path.join(ctx.workdir, f"{name}.tex"), tex)
        res = compile_latex(ctx.workdir, name, engine=ctx.engine)
        if res["ok"] and not res["errors"]:
            return tex, res["pdf"]
        if res["ok"] and attempt == max_fixes:
            return tex, res["pdf"]
        if attempt == max_fixes:
            break
        ctx.log(f"   🔧 compile issues in {name} (attempt {attempt + 1}); asking writer to repair …")
        errs = "\n".join(res["errors"][:12]) or "PDF not produced; see log."
        tex = ctx.writer.generate(P.COMPILE_FIX_PROMPT.format(errors=errs, latex=tex), temperature=0.1,
                                  agent="compile_fix", parser=parse_latex)
    return tex, None


# =============================================================================
# 6. Review + content refinement (accept / revert logic from paper-orchestra)
# =============================================================================

AXES = ["Originality", "Quality", "Clarity", "Significance", "Soundness", "Presentation", "Contribution",
        "Overall", "Confidence"]


def review_paper(ctx: Ctx, pdf_path: str, n_ensemble: int = 1) -> dict:
    text = pdf_text(pdf_path)
    prompt = P.REVIEW_INSTRUCTIONS + f"\n\nHere is the paper you are asked to review:\n```\n{text}\n```"
    reviews = [ctx.reviewer.generate(prompt, system=P.reviewer_system_prompt(ctx.profile), temperature=0.75,
                                     agent="reviewer", parser=parse_json) for _ in range(max(1, n_ensemble))]
    review = dict(reviews[0])
    if len(reviews) > 1:
        import statistics
        for ax in AXES:
            vals = [int(r[ax]) for r in reviews if str(r.get(ax, "")).strip().lstrip("-").isdigit()]
            if vals:
                review[ax] = round(statistics.mean(vals))
        review["Weaknesses"] = sum((r.get("Weaknesses", []) for r in reviews), [])
        review["Questions"] = sum((r.get("Questions", []) for r in reviews), [])
    return review


def _scores(r: dict) -> dict:
    out = {}
    for a in AXES:
        try:
            out[a] = float(r.get(a, 0))
        except (TypeError, ValueError):
            out[a] = 0.0
    return out


def run_refinement(ctx: Ctx, tex: str, pdf: str, cmap: dict, guidelines: str, rounds: int = 2,
                   n_ensemble: int = 1) -> tuple[str, str, dict]:
    ctx.log("🔍 [5/6] Content refinement: simulated peer review → revision loop …")
    rev_dir = os.path.join(ctx.workdir, "..", "peer_reviews")
    os.makedirs(rev_dir, exist_ok=True)
    review = review_paper(ctx, pdf, n_ensemble)
    write(os.path.join(rev_dir, "review_v0.json"), json.dumps(review, indent=2, ensure_ascii=False))
    ctx.log(f"   → initial reviewer score: {review.get('Overall')}/10 ({review.get('Decision')})")
    worklog = {"initial_review": _scores(review)}
    cur_tex, cur_pdf, cur_review = tex, pdf, review
    for i in range(rounds):
        user = f"""REFLECTION ITERATION {i + 1}.
--- PREVIOUS ITERATION LOG ---
{json.dumps(worklog, indent=1)}
--- CURRENT REVIEWER FEEDBACK (Overall {cur_review.get('Overall')}) ---
{json.dumps(cur_review, indent=1, ensure_ascii=False)}
--- GUIDELINES ---
{guidelines}
--- EXPERIMENTAL LOG (data truth) ---
{ctx.material('experimental_log.md')}
--- CITATION LIBRARY (allowed keys) ---
{citation_library_text(cmap)}
--- CURRENT LATEX SOURCE ---
{cur_tex}
INSTRUCTION: improve the paper by addressing weaknesses and questions; output worklog JSON then full LaTeX."""
        try:
            out = ctx.writer.generate(user, system=P.refinement_prompt(ctx.profile), attachments=[cur_pdf],
                                      temperature=0.5, agent="refiner", parser=parse_json_and_latex)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"   ⚠️ refinement failed: {e}")
            break
        new_tex, new_pdf = compile_with_repair(ctx, out["latex"], f"refined_v{i + 1}")
        if not new_pdf:
            ctx.log("   ⚠️ revised draft failed to compile — keeping previous version")
            continue
        new_review = review_paper(ctx, new_pdf, n_ensemble)
        write(os.path.join(rev_dir, f"review_v{i + 1}.json"), json.dumps(new_review, indent=2, ensure_ascii=False))
        old, new = _scores(cur_review), _scores(new_review)
        deltas = {k: new[k] - old[k] for k in AXES if k not in ("Overall", "Confidence")}
        gain = sum(d for d in deltas.values() if d > 0)
        drop = -sum(d for d in deltas.values() if d < 0)
        entry = {"round": i + 1, "plan": out["json"], "before": old, "after": new, "deltas": deltas}
        if new["Overall"] > old["Overall"] or (new["Overall"] == old["Overall"] and gain >= drop):
            entry["outcome"] = "ACCEPTED"
            cur_tex, cur_pdf, cur_review = new_tex, new_pdf, new_review
            ctx.log(f"   ✅ round {i + 1}: {old['Overall']} → {new['Overall']} (accepted)")
            worklog[f"v{i + 1}"] = entry
        else:
            entry["outcome"] = "REVERTED"
            worklog[f"v{i + 1}"] = entry
            ctx.log(f"   ↩️ round {i + 1}: {old['Overall']} → {new['Overall']} (reverted, stop)")
            break
    write(os.path.join(rev_dir, "refinement_worklog.json"), json.dumps(worklog, indent=2, ensure_ascii=False))
    return cur_tex, cur_pdf, cur_review


# =============================================================================
# 7. Format refinement (vision)
# =============================================================================

def run_format(ctx: Ctx, tex: str, pdf: str, guidelines: str) -> tuple[str, str, dict]:
    ctx.log("📐 [6/6] Format agent: visual layout check of the compiled PDF …")
    grids = pdf_to_grid_images(pdf, os.path.join(ctx.workdir, "..", "page_previews"))
    fb = ctx.reviewer.generate(P.format_review_prompt(guidelines), attachments=grids[:8], temperature=0.2,
                               agent="format_review", parser=parse_json)
    issues = [v for v in (fb.get("figure_and_tables") or {}).values()
              if isinstance(v, dict) and str(v.get("detected_issue", "none")).lower() != "none"]
    issues += [x for x in (fb.get("other_issues") or []) if isinstance(x, dict)
               and str(x.get("detected_issue", "none")).lower() != "none"]
    if not issues:
        ctx.log("   → no formatting issues detected")
        return tex, pdf, fb
    ctx.log(f"   → {len(issues)} formatting issue(s); fixing …")
    new = ctx.writer.generate(P.FORMAT_FIX_PROMPT.format(feedback=json.dumps(fb, indent=1, ensure_ascii=False),
                                                         guidelines=guidelines, latex=tex),
                              temperature=0.1, agent="format_fix", parser=parse_latex)
    new_tex, new_pdf = compile_with_repair(ctx, new, "formatted")
    if new_pdf:
        return new_tex, new_pdf, fb
    return tex, pdf, fb
