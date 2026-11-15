"""LaTeX compilation and PDF utilities (adapted from paper-orchestra utils/pdf_utils.py)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Optional


def compile_latex(work_dir: str, tex_name: str, engine: str = "pdflatex", timeout: int = 120) -> dict:
    """Compile ``work_dir/tex_name.tex`` with engine + bibtex. Returns dict(ok, pdf, errors, log)."""
    pdf = os.path.join(work_dir, f"{tex_name}.pdf")
    if os.path.exists(pdf):
        os.remove(pdf)
    env = {k: v for k, v in os.environ.items()
           if k not in ("TEXINPUTS", "TEXMFHOME", "TEXMF", "TEXMFVAR", "TEXMFCONFIG")}
    run = [engine, "-interaction=nonstopmode", "-file-line-error", f"{tex_name}.tex"]
    cmds = [run, ["bibtex", tex_name], run, run]
    logs = []
    for c in cmds:
        try:
            r = subprocess.run(c, cwd=work_dir, capture_output=True, text=True, timeout=timeout, env=env,
                               errors="replace")
            logs.append((" ".join(c), r.returncode, r.stdout[-6000:]))
        except subprocess.TimeoutExpired:
            logs.append((" ".join(c), -1, f"TIMEOUT after {timeout}s"))
            break
    log_path = os.path.join(work_dir, f"{tex_name}.log")
    log_txt = open(log_path, encoding="utf-8", errors="replace").read() if os.path.exists(log_path) else ""
    return {"ok": os.path.exists(pdf), "pdf": pdf if os.path.exists(pdf) else None,
            "errors": extract_errors(log_txt), "warnings": extract_warnings(log_txt),
            "steps": [(c, rc) for c, rc, _ in logs]}


def extract_errors(log: str, limit: int = 15) -> list[str]:
    errs = []
    lines = log.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("!") or re.match(r"^[^:\s]+\.tex:\d+:", ln):
            errs.append("\n".join(lines[i:i + 3]))
        if len(errs) >= limit:
            break
    return errs


def extract_warnings(log: str) -> dict:
    return {
        "undefined_citations": sorted(set(re.findall(r"Citation `([^']+)' on page", log))),
        "undefined_references": sorted(set(re.findall(r"Reference `([^']+)' on page", log))),
        "overfull_boxes": len(re.findall(r"Overfull \\hbox \((\d+\.\d+)pt too wide", log)),
        "missing_files": sorted(set(re.findall(r"File `([^']+)' not found", log))),
    }


def pdf_text(pdf_path: str, max_pages: Optional[int] = None) -> str:
    """Plain text extraction (no OCR) — fast and sufficient for LLM review."""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    return "\n".join(f"<<page {i + 1}>>\n" + page.get_text() for i, page in enumerate(doc)
                     if max_pages is None or i < max_pages)


def pdf_num_pages(pdf_path: str) -> int:
    import pymupdf
    return len(pymupdf.open(pdf_path))


def pdf_to_grid_images(pdf_path: str, out_dir: str, scale: float = 1.6) -> list[str]:
    """Render pages into 2x2 grid PNGs (as in paper-orchestra) for vision-based format checks."""
    import numpy as np
    import pymupdf
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    imgs = []
    for page in doc:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        imgs.append(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[..., :3])
    paths = []
    for i in range(0, len(imgs), 4):
        chunk = imgs[i:i + 4]
        h = max(x.shape[0] for x in chunk)
        w = max(x.shape[1] for x in chunk)
        pad = [np.pad(x, ((0, h - x.shape[0]), (0, w - x.shape[1]), (0, 0)), constant_values=255) for x in chunk]
        while len(pad) < 4:
            pad.append(np.full((h, w, 3), 255, dtype=np.uint8))
        grid = np.vstack((np.hstack(pad[:2]), np.hstack(pad[2:])))
        p = os.path.join(out_dir, f"grid_{i // 4 + 1}.png")
        Image.fromarray(grid).save(p)
        paths.append(p)
    return paths


def copy_template(template_dir: str, dest: str):
    shutil.copytree(template_dir, dest, dirs_exist_ok=True)
