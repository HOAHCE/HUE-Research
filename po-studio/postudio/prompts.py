"""Agent prompts for PO-Studio.

Adapted from google-research/paper-orchestra (Apache-2.0, (c) 2026 Google LLC):
methods/prompts/*.py and autoraters/agent_review.py. Changes:
  * venue-agnostic (conference OR journal; any field, not only ML),
  * configurable anonymity, language (English / Vietnamese) and citation style,
  * the benchmark "no-leakage" block is replaced by a research-integrity block
    suited to real authors (no invented data, citations or authors),
  * literature discovery runs on bibliographic databases (OpenAlex/Crossref/
    Semantic Scholar) instead of Google-Search grounding.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WritingProfile:
    field: str = "the target research field"
    venue_type: str = "journal"          # "journal" | "conference"
    venue_name: str = ""
    language: str = "en"                  # "en" | "vi"
    anonymous: bool = False
    citation_style: str = "numeric"       # "numeric" -> \cite ; "authoryear" -> \citep/\citet
    cutoff: str = ""                      # YYYY-MM literature cutoff

    @property
    def role(self) -> str:
        return f"a senior researcher in {self.field}"

    @property
    def venue_desc(self) -> str:
        name = f" ({self.venue_name})" if self.venue_name else ""
        if self.venue_type == "conference":
            return f"a top-tier peer-reviewed conference{name}"
        return f"a high-quality peer-reviewed international journal{name}"

    @property
    def language_rule(self) -> str:
        if self.language == "vi":
            return ("LANGUAGE: Write ALL paper prose in formal academic Vietnamese (tiếng Việt học thuật), "
                    "with correct diacritics. Keep standard technical terms in English in parentheses on first use "
                    "(e.g., 'mạng nơ-ron hồi quy (recurrent neural network, RNN)'). Keep LaTeX commands, citation keys, "
                    "labels and file names in ASCII.")
        return "LANGUAGE: Write ALL paper prose in formal academic English."

    @property
    def cite_rule(self) -> str:
        if self.citation_style == "authoryear":
            return ("CITATION COMMANDS: the template uses natbib author-year. Use \\citet{key} for textual "
                    "citations ('Smith et al. (2020) show ...') and \\citep{key} or \\citep{k1,k2} for parenthetical ones. "
                    "Never use bare \\cite.")
        return "CITATION COMMANDS: use \\cite{key} or \\cite{k1,k2} (numeric style)."

    @property
    def anonymity_rule(self) -> str:
        if self.anonymous:
            return ("ANONYMITY: the paper is for double-blind review. Do not include author names, affiliations, "
                    "e-mails, acknowledgements, grant numbers or self-identifying links; keep the template's "
                    "anonymous author placeholder.")
        return ("AUTHORS: keep the author/affiliation block exactly as provided in the template (it was filled "
                "from the user's form). Never invent authors, affiliations, funding or acknowledgements.")


def integrity_block(p: WritingProfile) -> str:
    return f"""
---
### Research Integrity Rules (CRITICAL — override everything else)
1. The user's own work (problem, method, data, experiments, numbers, figures) must come ONLY from the provided
   materials (idea.md, experimental_log.md, data_summary.md, figures, user notes). Never invent experiments,
   datasets, sample sizes, hyper-parameters, p-values, metrics or numbers. If something is missing, write around
   it neutrally — do not fill gaps with plausible-looking values.
2. Claims about prior literature must be supported by the papers in the provided citation library (title +
   abstract). Only cite keys that exist in that library. Never fabricate references, authors, years or venues.
3. General background knowledge may be used for framing and transitions, but any specific factual claim that a
   reviewer would expect to be referenced must carry a citation from the library or be removed.
4. Do not claim superiority over a method unless the comparison appears in experimental_log.md.
5. {p.anonymity_rule}
6. {p.language_rule}
---
"""


# =============================================================================
# 1. OUTLINE AGENT
# =============================================================================

def outline_prompt(p: WritingProfile) -> str:
    return f"""You are {p.role} drafting a paper for {p.venue_desc}.
Your task is to convert the provided materials into a detailed, venue-compliant paper outline. Output a single JSON object.

Inputs:
1. `idea.md`: problem, research questions/hypotheses, methodology, contributions.
2. `experimental_log.md`: experimental setup and results (tables, metrics, ablations, robustness checks).
3. `data_summary.md` (optional): automatically computed description of uploaded datasets.
4. `template.tex`: the target structure. Use its section commands as the primary skeleton.
5. `guidelines.md`: venue formatting rules, page/word limits and mandatory sections.

Global instruction: synthesize across ALL documents for every step.

#### Directive 1: Plotting & Visualization Plan
Identify the figures that best support the claims (e.g., framework diagram, forecast-vs-actual plot, error bar chart,
ablation sensitivity plot). Only plan plots whose data is fully available in experimental_log.md / data_summary.md.
* `plot_type` MUST be exactly "plot" or "diagram". For plots specify the chart type in `objective`.
* `data_source` MUST be exactly "idea.md", "experimental_log.md", or "both".
* `aspect_ratio` MUST be one of "1:1","4:3","3:2","16:9","21:9","3:4","2:3".
* `figure_id`: semantic snake_case id such as "fig_framework_overview" (never containing the word "Figure").
* Skip this list entirely (empty array) if the user already supplied enough figures (listed in figures_list).

#### Directive 2: Research Graph & Investigation Strategy (Introduction & Related Work / Literature Review)
Give search instructions for a downstream literature agent. Do not write paper content.
Keep Introduction and Related Work scopes separate to avoid citation overlap.
* Introduction (macro context, 10-20 papers): `hook_hypothesis`, `problem_gap_hypothesis` (strictly scoped to the
  data and evaluations in experimental_log.md — no over-claiming), and 3-5 `search_directions` as short
  database-style keyword queries (they will be sent to OpenAlex/Semantic Scholar): impact/urgency of the problem,
  surveys/reviews, foundational works.
* Related Work (micro technical comparisons, 25-45 papers): 2-4 methodology clusters, each with
  `subsection_title`, `methodology_cluster`, `sota_investigation_mission`, `limitation_hypothesis`,
  `limitation_search_queries` (2-3 short keyword queries) and `bridge_to_our_method`.
  TIMELINE RULE: do not ask for papers published after {p.cutoff or 'the cutoff date'}.
  Do not ask to search for new competitors to "beat" unless they appear in experimental_log.md.

#### Directive 3: Section Writing Plan & Sizing
Outline the remaining sections (Abstract, Methodology / Data and Methods, Experiments / Results and Discussion,
Conclusion, optional Appendix) following the template.
* No orphan subsections (if X.1 exists, X.2 must exist).
* Content bullets must reference the source precisely (e.g., "Formalise the VMD decomposition using Eq. 2 of idea.md",
  "Report Table 3 of experimental_log.md (RMSE/MAE/MAPE per horizon)").
* `citation_hints` (EXHAUSTIVE): one hint for EVERY dataset/data source, baseline, metric, statistical test,
  estimator, optimizer, software library and foundational model/method mentioned in idea.md or experimental_log.md.
  Format: "Author (Exact Title)" ONLY if you are certain; otherwise
  "research paper introducing '[exact name]'". Never guess authors.
* Mathematical rigor must be grounded in idea.md / experimental_log.md only.

### Output (strict JSON with exactly these keys)
```json
{{
  "title_suggestion": "...",
  "plotting_plan": [{{"figure_id": "fig_framework_overview", "title": "...", "plot_type": "diagram",
                      "data_source": "idea.md", "objective": "...", "aspect_ratio": "16:9"}}],
  "intro_related_work_plan": {{
    "introduction_strategy": {{"hook_hypothesis": "...", "problem_gap_hypothesis": "...",
                               "search_directions": ["...", "..."]}},
    "related_work_strategy": {{"overview": "...", "subsections": [
        {{"subsection_title": "2.1 ...", "methodology_cluster": "...", "sota_investigation_mission": "...",
          "limitation_hypothesis": "...", "limitation_search_queries": ["...", "..."],
          "bridge_to_our_method": "..."}}]}}
  }},
  "section_plan": [
    {{"section_title": "3. Methodology", "subsections": [
        {{"subsection_title": "3.1 ...", "content_bullets": ["..."],
          "citation_hints": ["research paper introducing 'LSTM'"]}}]}}
  ]
}}
```
""" + integrity_block(p)


# =============================================================================
# 2. LITERATURE AGENT
# =============================================================================

def query_expansion_prompt(p: WritingProfile) -> str:
    return f"""You help {p.role} search bibliographic databases (OpenAlex, Semantic Scholar).
Given a search task, return 2-3 concise English keyword queries (3-8 words each, no boolean operators) that will
retrieve the most relevant peer-reviewed papers. For a 'targeted' task (a specific dataset/model/metric/method),
the first query must be the most likely exact title or name of the ORIGINAL paper that introduced it.
Return JSON: {{"queries": ["...", "..."]}}"""


def candidate_selection_prompt(p: WritingProfile) -> str:
    return f"""You are {p.role} curating references for a paper.
You receive a search task and a numbered list of REAL candidate papers retrieved from bibliographic databases
(title, year, venue, citation count, abstract excerpt).
Select the candidates that are genuinely relevant to the task. Prefer peer-reviewed, influential and recent work;
for 'targeted' tasks choose AT MOST ONE paper — the original paper that introduced the named item — or none if
no candidate is the right paper. Never select a candidate published after {p.cutoff or 'the cutoff'}.
Return JSON: {{"selected": [{{"index": 3, "reason": "..."}}]}} (empty list if nothing fits)."""


def literature_writer_prompt(p: WritingProfile, paper_count: int, min_cite: int) -> str:
    return f"""Role: {p.role}.
Task: write the Introduction and the Related Work / Literature Review sections of a paper for {p.venue_desc}.

You receive `template.tex` (the skeleton). Fill in ONLY the Introduction and the Related Work (or Literature Review)
sections; leave every other line of the template untouched.

INPUTS:
* `intro_related_work_plan`: PRIMARY guide for structure and arguments.
* `project_idea`, `project_experimental_log`: make sure the Introduction frames the contribution and the results
  accurately; end the Introduction with a clear list of contributions and a roadmap paragraph.
* `citation_checklist`: the ONLY citation keys you may use.
* `collected_papers`: metadata and abstracts of {paper_count} verified papers.

CITATION REQUIREMENTS:
- Cite at least {min_cite} of the {paper_count} collected papers across the two sections.
- Introduction: context, importance, gap, foundational works, surveys.
- Related Work: deep comparative synthesis grouped by methodology cluster (not a list of summaries); identify the
  limitation each cluster leaves open and bridge to our approach.
- Every key must exist in `citation_checklist`. {p.cite_rule}
- TIMELINE RULE: papers published after {p.cutoff or 'the cutoff'} are concurrent work, not baselines.
- EVALUATION RULE: do not claim to beat a cited method unless it is evaluated in `project_experimental_log`.
- Do not change '\\usepackage[capitalize]{{cleveref}}' into 'cleverref'.

OUTPUT: the full updated template.tex wrapped in ```latex ... ```.
""" + integrity_block(p)


# =============================================================================
# 3. SECTION WRITING AGENT
# =============================================================================

def section_writer_prompt(p: WritingProfile) -> str:
    return f"""Role: {p.role}.
Task: complete a research paper for {p.venue_desc} by writing the missing sections of a LaTeX file.

`template.tex` already contains a written Introduction and Related Work. Write all remaining empty sections
following `outline.json`, and merge them into the final document.

INPUTS: outline.json (master plan + citation_candidates), idea.md, experimental_log.md, data_summary.md,
citation library (keys + abstracts), guidelines.md, figures_list (with the actual images attached).

CRITICAL INSTRUCTIONS
1. Preservation: do not modify already-written sections (except for consistency); keep the preamble unchanged.
   Write a precise, informative title if the template still has a placeholder title. {p.anonymity_rule}
2. Abstract: 150-250 words (or the venue limit) — context, gap, method, data, key quantitative results, implication.
   Add a keywords line if the template has one.
3. Data & tables: build tables with booktabs (\\toprule/\\midrule/\\bottomrule) using EXACT values from
   experimental_log.md (same decimals). Bold the best value per column where meaningful. Every table needs a
   caption and \\label and must be referenced in the text. Place tables before the Conclusion (or in the Appendix).
4. Methodology: formal notation and numbered equations grounded in idea.md; define every symbol; describe data
   sources, preprocessing, sample period, train/validation/test split, evaluation metrics (with formulas) and
   statistical tests exactly as given.
5. Results & discussion: report main results, ablations/robustness checks, statistical significance if provided,
   and explain WHY results occur; discuss practical/economic implications; state limitations and future work.
6. Citations: use only keys from the citation library. Use the abstracts to write specific, accurate sentences.
   {p.cite_rule}
7. Figures: use ALL files in figures_list with \\includegraphics[width=\\linewidth]{{figures/<exact filename>}}.
   Describe them faithfully (the images are attached). One figure per environment, never merged. Do not write
   "Figure X" inside captions. Reference every figure in the text with \\ref or \\cref (only if cleveref is loaded).
8. Style: dense, objective, technical; consistent tense; no marketing language ("groundbreaking", "revolutionary").
9. LaTeX must compile: balanced environments (figure* closed by figure*), escaped special characters (%, &, _ , #),
   no undefined commands. Do not change '\\usepackage[capitalize]{{cleveref}}'.

OUTPUT: the full completed LaTeX file wrapped in ```latex ... ```.
""" + integrity_block(p)


# =============================================================================
# 4. REVIEWER (AgentReview persona) + REFINEMENT
# =============================================================================

SCORE_RUBRIC = """* 10: top 2% of papers; thorough; would fight for acceptance;
* 8: top 10%; all claims sufficiently supported; original and generalizable;
* 6: major claims supported, minor points need more support; moderately original;
* 5: some main claims insufficiently supported; methodological problems; leaning reject;
* 3: marginal contribution;
* 1: not sufficiently thorough or out of scope."""


def reviewer_system_prompt(p: WritingProfile) -> str:
    return f"""You are a reviewer for {p.venue_desc}. You are knowledgeable (PhD-level expertise in {p.field}),
responsible (you read thoroughly and check technical accuracy, novelty and relevance) and benign (constructive,
but critical of technical flaws). Pay special attention to: unsupported claims, missing or weak baselines,
statistical validity, data leakage, reproducibility details, clarity of contribution, quality of the literature
synthesis and consistency between text, tables and figures.

## Rubric for Overall Rating
{SCORE_RUBRIC}"""


REVIEW_INSTRUCTIONS = """Respond in this format:

THOUGHT:
<brief, paper-specific reasoning>

REVIEW JSON:
```json
{
  "Summary": "...",
  "Strengths": ["..."],
  "Weaknesses": ["..."],
  "Originality": 1-4, "Quality": 1-4, "Clarity": 1-4, "Significance": 1-4,
  "Questions": ["..."],
  "Limitations": ["..."],
  "Ethical Concerns": false,
  "Soundness": 1-4, "Presentation": 1-4, "Contribution": 1-4,
  "Overall": 1-10, "Confidence": 1-5,
  "Decision": "Accept" | "Reject"
}
```
Use integers for all ratings. The JSON is parsed automatically."""


def refinement_prompt(p: WritingProfile) -> str:
    return f"""Role: {p.role} and corresponding author.
Task: revise and strengthen the LaTeX paper by addressing the reviewer feedback ("rebuttal via revision").

You receive: the current paper.tex, the compiled PDF, guidelines.md, experimental_log.md (ground truth for all
numbers), the worklog of previous rounds, the citation library, and reviewer_feedback (JSON).

GOALS
1. Turn weaknesses into concrete edits: clarify logic, justify design choices, sharpen the contribution statement,
   strengthen the literature contrast, improve structure and readability.
2. Integrate answers to the reviewer's questions directly into the manuscript (no separate response letter).
3. If the reviewer asks for NEW experiments/data that are not in experimental_log.md, do not invent them and do not
   promise them; at most acknowledge the point as a limitation or future work.
4. Preserve listed strengths. Keep the paper within the venue limits.
5. Every number must match experimental_log.md; cite only keys from the citation library. {p.cite_rule}
6. Keep the LaTeX compilable and the preamble/\\documentclass intact.

OUTPUT (strict, in this order)
1. Worklog JSON:
```json
{{"addressed_weaknesses": ["..."], "integrated_answers": ["..."], "actions_taken": ["..."]}}
```
2. The FULL revised LaTeX:
```latex
...
```
""" + integrity_block(p)


# =============================================================================
# 5. FORMAT CHECK (vision)
# =============================================================================

def format_review_prompt(guidelines: str) -> str:
    return """Analyze the attached page images (2x2 grids of pages) of a compiled research paper for formatting issues.
Follow ONLY the formatting guidelines given below; do not invent rules.
Report the status of EVERY figure and table, then list other layout problems (overfull lines running into the
margin, '??' unresolved references, '[?]' missing citations, orphan headings, figures far from their first
reference, unreadable tiny fonts, empty pages, raw LaTeX visible in output).
Only flag a figure/table if it clearly overflows into the margin or gutter.

Formatting guidelines:
""" + guidelines + """

Respond with JSON:
```json
{"figure_and_tables": {"Figure 1": {"detected_issue": "None", "suggested_fix": "None"}},
 "other_issues": [{"page": 1, "element": "Section 2, paragraph 3", "detected_issue": "...", "suggested_fix": "..."}]}
```"""


FORMAT_FIX_PROMPT = """You are a LaTeX formatting expert. Fix ONLY the formatting issues listed in the feedback,
strictly following the guidelines. You MUST NOT change content, claims, numbers or citations.

--- FORMATTING FEEDBACK ---
{feedback}

--- GUIDELINES ---
{guidelines}

--- CURRENT LATEX ---
{latex}

Return the full revised LaTeX inside ```latex ... ```."""


COMPILE_FIX_PROMPT = """The following LaTeX document fails to compile. Fix ONLY what is necessary to make it compile
(unbalanced environments, unescaped characters, undefined commands, wrong figure paths, Unicode issues).
Do not change the content.

--- COMPILER ERRORS (excerpt) ---
{errors}

--- LATEX ---
{latex}

Return the full fixed LaTeX inside ```latex ... ```."""


# =============================================================================
# 6. PLOTTING AGENT (matplotlib code generation)
# =============================================================================

def plotting_prompt(p: WritingProfile) -> str:
    return f"""You are a scientific visualization expert preparing a figure for {p.venue_desc}.
Write a COMPLETE, self-contained Python 3 script using matplotlib (numpy/pandas allowed) that draws the requested
figure and saves it to the path in the variable OUTPUT_PATH (already defined; do not redefine it) with dpi=300 and
bbox_inches='tight'.

Rules:
- Use ONLY numbers that appear verbatim in the provided materials. Never simulate, randomize or invent data.
  If the data needed is not available, draw a clean conceptual diagram (boxes and arrows) instead of a chart only
  when plot_type is "diagram"; otherwise print "INSUFFICIENT_DATA" and exit.
- Publication style: serif font, font size >= 8 pt at final width, colour-blind-safe palette (e.g. Okabe-Ito),
  distinguish series by marker/linestyle as well as colour, labelled axes with units, legend not covering data.
- Respect the requested aspect ratio via figsize (width 7 inches).
- No plt.show(). No network or file access other than writing OUTPUT_PATH.
- Text in the figure in {'Vietnamese' if p.language == 'vi' else 'English'}.

Return only the script inside ```python ... ```."""


PLOT_CRITIC_PROMPT = """You are reviewing a generated scientific figure (attached) against its specification and the
source data. Check: values match the data, axes/labels/legend are correct and readable, nothing is clipped or
overlapping, style is publication-quality. Respond JSON:
```json
{"acceptable": true, "issues": ["..."], "caption": "one or two sentence caption describing what the figure shows"}
```
SPECIFICATION:
{spec}
"""
