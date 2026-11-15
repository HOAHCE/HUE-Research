"""Deterministic fake LLM used by tests (`--writer-model mock`).

It produces structurally valid outputs for every agent so the whole pipeline
(literature registry, LaTeX assembly, compilation, review loop, packaging)
can be exercised offline without API keys. The text is obviously synthetic.
"""
from __future__ import annotations

import json
import re

_COUNTER = {"review": 0}


def _between(s: str, start: str, end: str | None = None) -> str:
    i = s.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = s.find(end, i) if end else -1
    return s[i:j] if j > 0 else s[i:]


def _fill(tex: str, marker: str, body: str) -> str:
    pat = re.compile(rf"(%%%%%%%%% {marker} %%%%%%%%%\n)(.*?)(\n%%%%%%%%% {marker} %%%%%%%%%)", re.DOTALL)
    return pat.sub(lambda m: m.group(1) + body + m.group(3), tex, count=1)


def _cite(system: str, keys: list) -> str:
    if not keys:
        return ""
    cmd = "citep" if "\\citep" in system else "cite"
    return f"\\{cmd}{{{','.join(keys)}}}"


def mock_response(prompt: str, system: str, agent: str) -> str:
    if agent == "outline":
        return "```json\n" + json.dumps({
            "title_suggestion": "A Mock Study of Hybrid Forecasting Models",
            "plotting_plan": [{"figure_id": "fig_error_comparison", "title": "Error comparison", "plot_type": "plot",
                               "data_source": "experimental_log.md", "objective": "Bar chart of RMSE per model",
                               "aspect_ratio": "16:9"}],
            "intro_related_work_plan": {
                "introduction_strategy": {"hook_hypothesis": "Forecasting matters.",
                                          "problem_gap_hypothesis": "Hybrid models are under-explored.",
                                          "search_directions": ["time series forecasting survey",
                                                                "deep learning financial forecasting"]},
                "related_work_strategy": {"overview": "Two clusters.", "subsections": [
                    {"subsection_title": "2.1 Statistical models", "methodology_cluster": "ARIMA family",
                     "sota_investigation_mission": "find", "limitation_hypothesis": "linearity",
                     "limitation_search_queries": ["ARIMA nonlinear limitations"], "bridge_to_our_method": "x"},
                    {"subsection_title": "2.2 Deep learning models", "methodology_cluster": "LSTM",
                     "sota_investigation_mission": "find", "limitation_hypothesis": "overfitting",
                     "limitation_search_queries": ["LSTM overfitting small data"], "bridge_to_our_method": "y"}]}},
            "section_plan": [
                {"section_title": "3. Methodology", "subsections": [
                    {"subsection_title": "3.1 Model", "content_bullets": ["Describe model"],
                     "citation_hints": ["research paper introducing 'LSTM'"]},
                    {"subsection_title": "3.2 Metrics", "content_bullets": ["RMSE"],
                     "citation_hints": ["research paper introducing 'Diebold-Mariano test'"]}]}]}, indent=1) + "\n```"
    if agent == "plotting":
        return """```python
import matplotlib.pyplot as plt
models = ['ARIMA', 'LSTM', 'Hybrid']
rmse = [0.0521, 0.0433, 0.0389]
fig, ax = plt.subplots(figsize=(7, 3.9))
ax.bar(models, rmse, color=['#E69F00', '#56B4E9', '#009E73'], hatch=['', '//', 'xx'])
ax.set_ylabel('RMSE'); ax.set_title('Test-set RMSE (mock)')
fig.savefig(OUTPUT_PATH, dpi=300, bbox_inches='tight')
```"""
    if agent == "plot_critic":
        return '```json\n{"acceptable": true, "issues": [], "caption": "Test-set RMSE of the compared models."}\n```'
    if agent == "lit_query":
        return '```json\n{"queries": ["forecasting models", "neural networks forecasting"]}\n```'
    if agent == "lit_select":
        n = len(re.findall(r"^\[\d+\]", prompt, flags=re.M))
        idx = [0] if "(targeted)" in prompt else list(range(min(3, n)))
        return "```json\n" + json.dumps({"selected": [{"index": i, "reason": "relevant (mock)"} for i in idx]}) + "\n```"
    if agent == "lit_writer":
        payload = json.loads(prompt[prompt.index("{"):])
        tex, keys = payload["template.tex"], payload["citation_checklist"]
        half = max(1, len(keys) // 2)
        tex = _fill(tex, "INTRODUCTION",
                    f"Forecasting is important {_cite(system, keys[:half])}. This mock introduction states the gap "
                    "and lists contributions.")
        tex = _fill(tex, "RELATED WORK",
                    f"Prior studies {_cite(system, keys[half:])} are reviewed here in a synthetic way.")
        return f"```latex\n{tex}\n```"
    if agent == "section_writer":
        tex = _between(prompt, "(DO NOT CHANGE EXISTING TEXT. FILL MISSING SECTIONS.) ---\n", "\nINSTRUCTION:")
        keys = re.findall(r"--- Key: (\S+) ---", prompt)
        figs = re.findall(r"Filename: (\S+)", prompt)
        nums = re.findall(r"\|\s*(\w+)\s*\|\s*([\d.]+)\s*\|", prompt)
        rows = "\n".join(f"{m} & {v} \\\\" for m, v in nums[:6]) or "Model & 0.0 \\\\"
        table = ("\\begin{table}[t]\\centering\\caption{Forecast accuracy.}\\label{tab:main}\n"
                 "\\begin{tabular}{lc}\\toprule Model & RMSE \\\\ \\midrule\n" + rows +
                 "\n\\bottomrule\\end{tabular}\\end{table}")
        figtex = "\n".join(f"\\begin{{figure}}[t]\\centering\\includegraphics[width=0.8\\linewidth]{{figures/{f}}}"
                           f"\\caption{{Mock figure.}}\\label{{fig:f{i}}}\\end{{figure}}" for i, f in enumerate(figs))
        figref = " ".join(f"\\cref{{fig:f{i}}}" for i in range(len(figs)))
        tex = _fill(tex, "ABSTRACT", "This mock abstract summarises the problem, method and results.")
        tex = _fill(tex, "METHOD", "We define the model $y_t = f(x_t) + \\varepsilon_t$ "
                                   f"{_cite(system, keys[-2:])}.")
        tex = _fill(tex, "EXPERIMENTS", f"\\cref{{tab:main}} reports the results. {figref}\n{table}\n{figtex}")
        tex = _fill(tex, "CONCLUSION", "The mock conclusion summarises findings and limitations.")
        return f"```latex\n{tex}\n```"
    if agent in ("compile_fix", "format_fix"):
        tex = _between(prompt, "--- LATEX ---\n") or _between(prompt, "--- CURRENT LATEX ---\n")
        tex = tex.split("\n\nReturn the full")[0]
        return f"```latex\n{tex}\n```"
    if agent == "reviewer":
        _COUNTER["review"] += 1
        o = 5 + min(_COUNTER["review"] - 1, 1)
        return ("THOUGHT: mock\nREVIEW JSON:\n```json\n" + json.dumps({
            "Summary": "Mock summary.", "Strengths": ["clear"], "Weaknesses": ["needs more detail on data"],
            "Originality": 2, "Quality": 2, "Clarity": 3, "Significance": 2, "Questions": ["What is the sample?"],
            "Limitations": ["mock"], "Ethical Concerns": False, "Soundness": 2, "Presentation": 3,
            "Contribution": 2, "Overall": o, "Confidence": 3, "Decision": "Reject"}) + "\n```")
    if agent == "refiner":
        tex = _between(prompt, "--- CURRENT LATEX SOURCE ---\n", "\nINSTRUCTION:")
        tex = tex.replace("The mock conclusion", "The revised mock conclusion")
        return ('```json\n{"addressed_weaknesses": ["data detail"], "integrated_answers": [], '
                '"actions_taken": ["edited conclusion"]}\n```\n```latex\n' + tex + "\n```")
    if agent == "format_review":
        return '```json\n{"figure_and_tables": {"Table 1": {"detected_issue": "None", "suggested_fix": "None"}}, "other_issues": []}\n```'
    return "mock"
