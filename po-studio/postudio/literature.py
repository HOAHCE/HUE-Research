"""Verified literature retrieval for PO-Studio.

Unlike the original paper-orchestra (Gemini + Google-Search grounding), every
reference here comes from a bibliographic database record (OpenAlex, optionally
Semantic Scholar) or from the user's own .bib file. The LLM only *selects* among
real candidates, so references cannot be hallucinated.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

import requests

OPENALEX = "https://api.openalex.org/works"
S2 = "https://api.semanticscholar.org/graph/v1/paper/search"
UA = {"User-Agent": "PO-Studio/0.1 (academic paper drafting; mailto:{mail})"}

STOP = {"the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "is", "are", "with", "by", "study",
        "using", "via", "from", "based", "towards", "toward", "into"}


@dataclass
class Paper:
    title: str
    authors: list
    year: Optional[int]
    venue: str = ""
    abstract: str = ""
    doi: str = ""
    citation_count: int = 0
    publication_date: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    entry_type: str = "article"
    source: str = "openalex"          # openalex | s2 | user | mock
    found_in_section: str = ""
    reason: str = ""
    citation_key: str = ""
    raw_bibtex: str = ""              # for user-supplied entries

    def norm_title(self) -> str:
        return re.sub(r"[^a-z0-9]", "", self.title.lower())


# --------------------------------------------------------------------------
# Database clients
# --------------------------------------------------------------------------

def _rebuild_abstract(inv: Optional[dict]) -> str:
    if not inv:
        return ""
    pos = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    return " ".join(w for _, w in sorted(pos))


def _cutoff_date(cutoff: str) -> str:
    """'2025-06' -> last day of that month as YYYY-MM-DD."""
    if not cutoff:
        return dt.date.today().isoformat()
    y, m = (int(x) for x in cutoff.split("-")[:2])
    nxt = dt.date(y + (m == 12), (m % 12) + 1, 1)
    return (nxt - dt.timedelta(days=1)).isoformat()


class LiteratureSearch:
    def __init__(self, cutoff: str = "", mailto: str = "", s2_key: str = "",
                 openalex_key: str = "", offline: bool = False, log: Callable = print):
        self.cutoff = cutoff
        self.mailto = mailto or os.environ.get("OPENALEX_MAILTO", "")
        self.s2_key = s2_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        self.openalex_key = openalex_key or os.environ.get("OPENALEX_API_KEY", "")
        self.offline = offline or os.environ.get("POSTUDIO_OFFLINE") == "1"
        self.log = log
        self._s2_lock = threading.Lock()
        self._s2_last = 0.0

    # ---------------- OpenAlex ----------------
    def openalex(self, query: str, n: int = 15) -> list[Paper]:
        if self.offline:
            return _mock_search(query, n)
        params = {
            "search": query,
            "filter": f"to_publication_date:{_cutoff_date(self.cutoff)},has_abstract:true",
            "per-page": n,
            "select": "id,doi,display_name,publication_year,publication_date,authorships,primary_location,"
                      "cited_by_count,abstract_inverted_index,type,biblio",
        }
        if self.mailto:
            params["mailto"] = self.mailto
        if self.openalex_key:
            params["api_key"] = self.openalex_key
        for attempt in range(3):
            try:
                r = requests.get(OPENALEX, params=params, timeout=30,
                                 headers={"User-Agent": UA["User-Agent"].format(mail=self.mailto or "n/a")})
                if r.status_code == 429:
                    time.sleep(2 + 2 * attempt)
                    continue
                r.raise_for_status()
                out = []
                for w in r.json().get("results", []):
                    if not w.get("display_name"):
                        continue
                    src = ((w.get("primary_location") or {}).get("source") or {})
                    b = w.get("biblio") or {}
                    pages = ""
                    if b.get("first_page"):
                        pages = b["first_page"] + (f"--{b['last_page']}" if b.get("last_page") else "")
                    typ = w.get("type") or "article"
                    out.append(Paper(
                        title=re.sub(r"<[^>]+>", "", w["display_name"]).strip(),
                        authors=[a["author"]["display_name"] for a in w.get("authorships", [])
                                 if a.get("author", {}).get("display_name")],
                        year=w.get("publication_year"),
                        venue=src.get("display_name") or "",
                        abstract=_rebuild_abstract(w.get("abstract_inverted_index"))[:1500],
                        doi=(w.get("doi") or "").replace("https://doi.org/", ""),
                        citation_count=w.get("cited_by_count") or 0,
                        publication_date=w.get("publication_date") or "",
                        volume=b.get("volume") or "", issue=b.get("issue") or "", pages=pages,
                        entry_type="inproceedings" if "proceedings" in (src.get("type") or "") or typ == "proceedings-article" else "article",
                        source="openalex"))
                return out
            except Exception as e:  # noqa: BLE001
                self.log(f"      ⚠️ OpenAlex error for '{query}': {e}")
                time.sleep(1 + attempt)
        return []

    # ---------------- Semantic Scholar (optional) ----------------
    def s2(self, query: str, n: int = 10) -> list[Paper]:
        if self.offline or not self.s2_key:
            return []
        with self._s2_lock:  # 1 req/s rate limit
            wait = 1.05 - (time.time() - self._s2_last)
            if wait > 0:
                time.sleep(wait)
            self._s2_last = time.time()
        try:
            r = requests.get(S2, headers={"X-API-KEY": self.s2_key}, timeout=20, params={
                "query": query, "limit": n,
                "fields": "title,authors,venue,year,abstract,citationCount,journal,publicationDate,externalIds"})
            if r.status_code != 200:
                return []
            out = []
            for d in r.json().get("data", []):
                if not d.get("title") or not d.get("abstract"):
                    continue
                if not self._before_cutoff(d.get("publicationDate"), d.get("year")):
                    continue
                j = d.get("journal") or {}
                out.append(Paper(title=d["title"], authors=[a["name"] for a in d.get("authors", [])],
                                 year=d.get("year"), venue=d.get("venue") or j.get("name") or "",
                                 abstract=d["abstract"][:1500],
                                 doi=(d.get("externalIds") or {}).get("DOI", "") or "",
                                 citation_count=d.get("citationCount") or 0,
                                 publication_date=d.get("publicationDate") or "",
                                 volume=j.get("volume") or "", pages=(j.get("pages") or "").replace("-", "--").strip(),
                                 source="s2"))
            return out
        except Exception as e:  # noqa: BLE001
            self.log(f"      ⚠️ S2 error: {e}")
            return []

    def _before_cutoff(self, pdate, pyear) -> bool:
        if not self.cutoff:
            return True
        lim = _cutoff_date(self.cutoff)
        if pdate:
            return pdate <= lim
        if pyear:
            return int(pyear) <= int(lim[:4])
        return True

    def search(self, query: str, n: int = 15) -> list[Paper]:
        res = self.openalex(query, n) + self.s2(query, max(5, n // 2))
        seen, out = set(), []
        for p in res:
            k = p.norm_title()
            if k and k not in seen:
                seen.add(k)
                out.append(p)
        return out


# --------------------------------------------------------------------------
# BibTeX utilities
# --------------------------------------------------------------------------

def make_key(p: Paper) -> str:
    first = p.authors[0] if p.authors else "Anon"
    last = first.split(",")[0] if "," in first else first.split()[-1]
    last = re.sub(r"[^A-Za-z]", "", _ascii(last)).capitalize() or "Anon"
    words = [w.capitalize() for w in re.sub(r"[^a-z0-9\s]", "", _ascii(p.title).lower()).split() if w not in STOP]
    return f"{last}{p.year or 'nd'}{''.join(words[:2]) or 'Paper'}"


def _ascii(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _bib_escape(s: str) -> str:
    s = s.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#").replace("_", r"\_")
    return s


def to_bibtex(p: Paper) -> str:
    if p.raw_bibtex:
        return re.sub(r"^(@\w+\{)\s*[^,]+,", rf"\g<1>{p.citation_key},", p.raw_bibtex.strip(), count=1)
    authors = " and ".join(p.authors) if p.authors else "Anonymous"
    fields = [("title", "{" + _bib_escape(p.title) + "}"), ("author", _bib_escape(authors)),
              ("year", str(p.year or ""))]
    if p.entry_type == "inproceedings":
        fields.append(("booktitle", _bib_escape(p.venue or "Proceedings")))
    else:
        fields.append(("journal", _bib_escape(p.venue or "Preprint")))
    for k in ("volume", "pages"):
        if getattr(p, k):
            fields.append((k, getattr(p, k)))
    if p.issue:
        fields.append(("number", p.issue))
    if p.doi:
        fields.append(("doi", p.doi))
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
    return f"@{p.entry_type}{{{p.citation_key},\n{body}\n}}"


def parse_bibtex(text: str) -> list[Paper]:
    """Minimal BibTeX parser for user-supplied reference lists."""
    papers = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", text, flags=re.DOTALL):
        etype, key, body = m.group(1).lower(), m.group(2), m.group(3)
        if etype in ("comment", "string", "preamble"):
            continue
        f = {}
        for fm in re.finditer(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|\d+)", body, flags=re.DOTALL):
            v = fm.group(2).strip()
            if v[0] in "{\"":
                v = v[1:-1]
            f[fm.group(1).lower()] = re.sub(r"\s+", " ", v.replace("{", "").replace("}", "")).strip()
        yr = re.search(r"\d{4}", f.get("year", ""))
        papers.append(Paper(
            title=f.get("title", key), authors=[a.strip() for a in f.get("author", "").split(" and ") if a.strip()],
            year=int(yr.group()) if yr else None, venue=f.get("journal") or f.get("booktitle") or "",
            abstract=f.get("abstract", "")[:1500], doi=f.get("doi", ""), source="user",
            entry_type=etype, citation_key=key, raw_bibtex=m.group(0),
            found_in_section="User-provided references", reason="Provided by the author"))
    return papers


# --------------------------------------------------------------------------
# Offline fixture (tests only)
# --------------------------------------------------------------------------

_MOCK_TOPICS = ["forecasting", "deep learning", "time series", "neural network", "volatility", "survey",
                "transformer", "decomposition", "benchmark", "evaluation metric"]


def _mock_search(query: str, n: int) -> list[Paper]:
    h = abs(hash(query)) % 1000
    out = []
    for i in range(min(n, 6)):
        t = _MOCK_TOPICS[(h + i) % len(_MOCK_TOPICS)]
        out.append(Paper(title=f"[TEST FIXTURE] A study of {t} for {query[:40]} ({h}-{i})",
                         authors=[f"Tester{(h + i) % 7} Alpha", "Beta Gamma"], year=2015 + (h + i) % 9,
                         venue="Journal of Test Fixtures", abstract=f"Synthetic abstract about {t} and {query}.",
                         doi=f"10.0000/test.{h}.{i}", citation_count=(h * (i + 1)) % 500, source="mock"))
    return out


# --------------------------------------------------------------------------
# Registry used by the literature agent
# --------------------------------------------------------------------------

class Registry:
    def __init__(self):
        self.papers: dict[str, Paper] = {}
        self.lock = threading.Lock()

    def add(self, p: Paper) -> bool:
        with self.lock:
            k = p.norm_title()
            if not k or k in self.papers:
                return False
            if not p.citation_key:
                p.citation_key = make_key(p)
            keys = {x.citation_key for x in self.papers.values()}
            base, suf = p.citation_key, ord("a")
            while p.citation_key in keys:
                p.citation_key = f"{base}{chr(suf)}"
                suf += 1
            self.papers[k] = p
            return True

    def bibtex(self) -> str:
        return "\n\n".join(to_bibtex(p) for p in self.papers.values()) + "\n"

    def citation_map(self) -> dict:
        return {p.citation_key: {"citation_key": p.citation_key, "title": p.title, "authors": p.authors,
                                 "venue": p.venue, "year": p.year, "doi": p.doi,
                                 "abstract": p.abstract.strip(), "source": p.source,
                                 "found_in_section": p.found_in_section}
                for p in self.papers.values()}

    def dump(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(p) for p in self.papers.values()], f, indent=2, ensure_ascii=False)
