# Elsevier journal (elsarticle) — writing guidelines

Compiled with elsarticle.cls (preprint, author-year, elsarticle-harv.bst). Requires texlive-publishers.

Use this template for journals in economics, finance, business informatics, information systems and applied
data science (Elsevier/Springer/Taylor & Francis/Emerald/MDPI style) when no venue-specific class is required.

## Language and length
* English, formal academic register. Target 7,000–9,000 words including references (adapt to the journal).
* Abstract: one paragraph, 150–250 words: purpose, design/methodology, findings (with key numbers),
  originality/value, practical implications. No citations in the abstract.
* 4–6 keywords separated by semicolons. Add JEL codes only if the user supplied them.

## Structure
1. Introduction — context, research gap, objectives/research questions, contributions (bulleted or numbered),
   paper organisation.
2. Literature Review — thematic synthesis (not a list of summaries); end with the gap and, where appropriate,
   hypotheses.
3. Data and Methodology — data sources, sample period, variables, preprocessing, models with numbered equations,
   estimation/training procedure, evaluation metrics and statistical tests.
4. Results and Discussion — descriptive statistics, main results, robustness/ablation, discussion relative to
   prior literature, practical/policy implications.
5. Conclusion — summary of findings, contributions, limitations, future research.
6. Declarations — keep exactly what the author provided; never invent funding, conflicts or data statements.

## Citations and references
* elsarticle author-year (natbib): `\citet{key}` in text ("Smith (2020) shows"), `\citep{key}` in parentheses.
* Only keys from references.bib. Typical length 40–70 references.

## Tables and figures
* booktabs tables; caption ABOVE tables, BELOW figures; numbers exactly as in the experimental log.
* Figures: `\includegraphics[width=0.9\linewidth]{figures/<file>}`; every table/figure referenced in the text.
* All figures live in the `figures/` directory; always include the `figures/` prefix.

## Important rules
* DO NOT change `\usepackage[capitalize]{cleveref}` into `cleverref`.
* Keep the preamble unchanged. Use `\cref{}` for cross-references.
