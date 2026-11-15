---
name: paper-orchestra-writer
description: Draft a complete, submission-ready research paper (LaTeX + PDF) from the user's idea, data, method and experimental results using the PaperOrchestra multi-agent workflow — outline, verified literature, section writing, simulated peer review, format check and integrity report. Use for "viết bài báo", "soạn bản thảo", "write my paper from these results", journal or conference manuscripts.
---

# Paper-Orchestra Writer

You act as the whole PaperOrchestra team (Google Research, arXiv:2604.05018): Outline agent → Plotting agent →
Literature agent → Section-writing agent → Reviewer/Refinement loop → Format agent, then run integrity checks and
deliver a LaTeX package + PDF. This skill mirrors the PO-Studio engine (`postudio`), so the same rules hold whether
you write the paper yourself or run the engine.

## Non-negotiable integrity rules

1. **Never invent results.** Every number, dataset, sample size, hyper-parameter, test statistic or p-value must come
   from the user's materials. If something is missing, ask (step 0) or write around it — never fill gaps with
   plausible values, and never "simulate" data for figures.
2. **Never cite a paper you have not verified exists.** Each reference must come from a database record
   (OpenAlex, Semantic Scholar, Crossref, PubMed, arXiv) or the user's own .bib, with a DOI/URL you have seen.
   Claims about a cited paper must be supported by its abstract or text you actually read.
3. Do not claim to beat a method unless that comparison is in the experimental log.
4. Never invent authors, affiliations, funding, ethics approvals or acknowledgements.
5. Add a "Use of generative AI" declaration (unless the venue is double-blind; then mention it in the hand-off).
   Tell the user the draft must be read and verified by them before submission.

## Step 0 — Intake (ask at most once, then proceed)

Collect into `work/raw_materials/`:
- `idea.md`: problem & motivation, research questions/hypotheses, contributions, methodology (models, equations,
  procedure, parameters), data description, notes on known related work/baselines.
- `experimental_log.md`: setup (splits, metrics, horizons, seeds, software), **results tables verbatim**, statistical
  tests, ablations/robustness, author's interpretation, limitations.
- `data_summary.md` (if data files are given): compute with pandas — observations, period, variables, missing values,
  descriptive statistics. Never alter values copied from result files (read CSV/XLSX with `dtype=str`).
- `figures/` + `figures/info.json` `[{"name": "...png", "caption": "..."}]` for user figures.
- `user_references.bib` if the user supplies references (they must be cited).
- Venue: target journal/conference, language (English / Vietnamese), anonymous or not, authors
  (name, affiliation, e-mail, corresponding), citation style, page/word limit, literature cutoff (YYYY-MM).

**Blocking gaps:** no method description, or no results at all → ask before writing. Everything else: take a
reasonable default, state it in one line, continue. If the user's materials live in files they only mention, ask for
them. If you know the user's research from context, reuse it but confirm numbers come from their files.

## Option A — Run the engine (fastest, needs an LLM API key and network)

If `postudio` is installed or its repo is available (`pip install -e <po-studio>`; check with `postudio templates`)
and an `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` is set:

```bash
postudio materials --form form.json --out work/raw_materials --data ... --results ... --figures f.png::"caption" --references refs.bib
postudio run --materials work/raw_materials --out work/run --template journal_generic \
  --writer-model claude-opus-5-5 --reviewer-model claude-sonnet-5-5 --venue "..." --authors authors.json --cutoff YYYY-MM
```
Then review `work/run/report.md`, open `final/paper.pdf` (render pages and look at them), fix anything flagged, and
deliver as in Step 9. Templates: `journal_generic`, `journal_vi`, `elsevier`, `ieee_journal`, `cvpr2025`, `iclr2025`.

## Option B — Write it yourself (no API key needed)

Track progress with a task list: Outline, Figures, Literature, Intro+RW, Sections, Compile, Review loop, Format,
Integrity, Deliver.

### Step 1 — Template

Use the venue's official class if available (`kpsewhich elsarticle.cls`, `IEEEtran.cls`, …) or the PO-Studio
templates. Otherwise use this generic journal template (author-year; for Vietnamese compile with **xelatex** and
replace the first three package lines by `\usepackage{fontspec}\setmainfont{TeX Gyre Termes}\usepackage[vietnamese]{babel}`
and rename sections: Giới thiệu, Tổng quan tài liệu, Dữ liệu và phương pháp nghiên cứu, Kết quả và thảo luận,
Kết luận, Tài liệu tham khảo; `\renewcommand{\figurename}{Hình}\renewcommand{\tablename}{Bảng}` inside `\AtBeginDocument`):

```latex
\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}\usepackage[T1]{fontenc}\usepackage{lmodern}
\usepackage[margin=2.5cm]{geometry}\usepackage{amsmath,amssymb,graphicx,booktabs,multirow,threeparttable}
\usepackage{caption,subcaption,xcolor,microtype,setspace,authblk}
\usepackage[round,authoryear]{natbib}
\usepackage[colorlinks=true,allcolors=blue!50!black]{hyperref}\usepackage[capitalize]{cleveref}
\onehalfspacing
\title{...}  \author[1]{...}  \affil[1]{...}  \date{}
\begin{document}\maketitle
\begin{abstract} ... \end{abstract}
\noindent\textbf{Keywords:} ...
\section{Introduction}\label{sec:intro}
\section{Literature Review}\label{sec:related_work}
\section{Data and Methodology}\label{sec:method}
\section{Results and Discussion}\label{sec:experiments}
\section{Conclusion}\label{sec:conclusion}
\section*{Declarations} % Funding / Conflict of interest / Data availability / Use of generative AI
\bibliographystyle{plainnat}\bibliography{references}
\end{document}
```

### Step 2 — Outline agent → `work/outline.json`

Synthesize all materials and produce JSON with exactly:
- `title_suggestion`
- `plotting_plan`: figures that prove the claims, only where data exists in the log
  (`figure_id` snake_case, `plot_type` "plot"|"diagram", `data_source`, `objective` incl. chart type, `aspect_ratio`).
- `intro_related_work_plan`:
  - `introduction_strategy`: `hook_hypothesis`, `problem_gap_hypothesis` (scoped strictly to the evaluated data —
    no over-claiming), 3–5 `search_directions` (short database keyword queries: impact of the problem, surveys,
    foundational works). Target 10–20 papers.
  - `related_work_strategy.subsections`: 2–4 methodology clusters, each with `methodology_cluster`,
    `sota_investigation_mission`, `limitation_hypothesis`, 2–3 `limitation_search_queries`, `bridge_to_our_method`.
    Target 25–45 papers. Intro = macro context, RW = micro technical comparison (no overlap).
- `section_plan`: remaining sections → subsections with precise `content_bullets` that reference the source
  ("Report Table 2 of experimental_log.md") and exhaustive `citation_hints` for EVERY dataset, baseline, metric,
  statistical test, estimator, optimizer, library and foundational model mentioned. Hint format: "Author (Exact
  Title)" only if certain, else "research paper introducing '<name>'". No orphan subsections.

### Step 3 — Plotting agent (only if the plan has figures and the user did not supply them)

For each planned figure write a matplotlib script that uses only numbers present verbatim in the materials,
publication style (serif, ≥8 pt at final size, Okabe-Ito colours plus markers/hatches, labelled axes with units,
width 7 in, dpi 300), save to `latex/figures/<figure_id>.png`. Then **look at the PNG** (Read it) and critique:
values match the data? labels readable? nothing clipped? Fix and re-render (max 2 rounds). Add to `info.json` with a
faithful caption. Conceptual diagrams: matplotlib boxes/arrows or TikZ.

### Step 4 — Literature agent → `references.bib` + `citation_map.json`

Run every search task: intro directions, every RW query, every citation hint (targeted → exactly the ORIGINAL paper
that introduced the item, or none). Tools, in order of preference:
1. `postudio lit-search "<query>" --cutoff YYYY-MM -n 15 [--bib]` (OpenAlex; needs network), or direct
   OpenAlex API: `https://api.openalex.org/works?search=<q>&filter=to_publication_date:<YYYY-MM-DD>,has_abstract:true&per-page=15`
   (abstract = rebuild `abstract_inverted_index`).
2. The `paper-lookup` / `citation-management` skills, or connected scholarly tools (Consensus, Elicit, alphaXiv,
   Semantic Scholar).
3. WebSearch + WebFetch of the DOI / publisher / arXiv page.

For each candidate keep only peer-reviewed or highly cited, relevant work published before the cutoff, with an
abstract you have read. Record in `citation_map.json`: key, title, authors, year, venue, DOI, abstract, source,
section found for. Keys: `LastnameYearFirstTwoWords` (ASCII). Build BibTeX from the record (title in double braces,
DOI field). Merge `user_references.bib` (keep the user's keys). Typical size: 40–60 papers for a journal paper;
never pad with weak papers.

### Step 5 — Write Introduction + Related Work

Follow `intro_related_work_plan`. Cite ≥90% of the library across these two sections; Introduction: context →
importance → gap → objective → numbered contributions → roadmap. Related Work: thematic synthesis per cluster,
grouped citations, explicit limitation of each cluster and the bridge to this work — not a list of summaries.
Papers after the cutoff are concurrent work. Use `\citet`/`\citep` (author-year) or `\cite` (numeric) consistently.

### Step 6 — Section-writing agent

Write Abstract (150–250 words: context, gap, method, data, key numbers, implication; no citations), Methodology
(formal notation, numbered equations grounded in idea.md, every symbol defined; data, preprocessing, splits,
metrics with formulas, tests), Results & Discussion (booktabs tables with EXACT log values and same decimals, best
value bold, caption above tables; every figure/table referenced; ablations/robustness; explain why; compare with
prior literature; practical/economic implications), Conclusion (findings, contributions, limitations, future work).
Style: dense, objective, no hype words. Escape `% & _ #`. Figures: `\includegraphics[width=0.9\linewidth]{figures/<file>}`.

### Step 7 — Compile and repair

```bash
cd latex && pdflatex -interaction=nonstopmode -file-line-error paper.tex && bibtex paper && pdflatex ... && pdflatex ...
# Vietnamese / Unicode: xelatex instead of pdflatex
grep -nE "^!|Citation .* undefined|Reference .* undefined|not found" paper.log
```
Fix every error, undefined citation/reference and missing file. Re-run until clean.

### Step 8 — Review ⇄ revision loop (max 2–3 rounds)

Act as an independent reviewer for the target venue (knowledgeable, responsible, constructive; extra attention to
unsupported claims, weak baselines, statistical validity, leakage, reproducibility, literature synthesis,
text/table consistency). Read the compiled PDF text (`pymupdf`), produce JSON: Summary, Strengths, Weaknesses,
Questions, Originality/Quality/Clarity/Significance/Soundness/Presentation/Contribution (1–4), Overall (1–10:
10 top 2%, 8 top 10%, 6 claims supported, 5 leaning reject, 3 marginal, 1 not ready), Confidence, Decision.
Save `reviews/review_vN.json`. Then revise as the author: address weaknesses, integrate answers to questions into
the text, ignore requests for new experiments (at most note them as limitations/future work), keep all numbers
equal to the log. Re-compile, re-review. **Accept** the revision if Overall rises, or stays equal with sub-score
gains ≥ drops; otherwise **revert** to the previous version and stop. Keep a worklog.

To reduce self-grading bias on high-stakes papers, run the reviewer as a separate subagent that has not seen the
writing process (only the PDF text + venue), if subagents are available and the user agrees.

### Step 9 — Format check (vision)

Render pages to PNG (`pymupdf`, 2x2 grids or single pages) and look at them: figures/tables overflowing margins,
`??` or `[?]`, raw LaTeX, orphan headings, figures far from first reference, tiny fonts, empty pages, page limit.
Fix layout only (no content changes), re-compile.

### Step 10 — Integrity checks (must pass before delivery)

Run `postudio check paper.tex --bib references.bib --materials raw_materials` or verify manually:
- every `\cite*` key exists in references.bib; no unverified entries; list uncited entries (remove or cite);
- every number inside `tabular` appears verbatim in experimental_log.md / data_summary.md;
- every `\includegraphics` file exists; every provided figure is used; every `\ref`/`\cref` label exists;
- no template placeholders; abstract within limit; page/word count within venue limit.

### Step 11 — Deliver

Package `final/` (paper.tex, references.bib, figures/, paper.pdf, any .cls/.bst/.sty) + `report.md`
(checks, reviewer scores, remaining weaknesses, items the author must complete — funding, conflicts, data
availability) into `submission_package.zip`. Send the PDF and the zip with SendUserFile. In the reply: one-line
summary, final reviewer score and the top 3 weaknesses the author should address, and the reminder to verify
citations and numbers and to disclose AI assistance. Reply in the user's language.
