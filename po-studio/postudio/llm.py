"""Unified LLM backend for PO-Studio.

Supports Anthropic Claude (default), Google Gemini and OpenAI, with text,
images (PNG/JPG) and PDF inputs. A deterministic ``mock`` backend is
provided for offline tests of the whole pipeline.

Model routing is by name prefix:
    claude-*            -> Anthropic
    gemini-*            -> Google GenAI
    gpt-*, o1*, o3*, o4* -> OpenAI
    mock*               -> MockLLM (tests)
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import json_repair


# --------------------------------------------------------------------------
# Parsing helpers (adapted from paper-orchestra utils/gemini_utils.py)
# --------------------------------------------------------------------------

def extract_block(text: str, lang: str) -> Optional[str]:
    """Return the LAST fenced block of the given language, or None."""
    pattern = rf"```{lang}\s*\n(.*?)```"
    blocks = re.findall(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip()
    return None


def parse_json(text: str) -> Any:
    block = extract_block(text, "json")
    candidate = block if block is not None else text
    try:
        return json.loads(candidate)
    except Exception:
        pass
    # fall back to first {...} or [...] span
    m = re.search(r"(\{.*\}|\[.*\])", candidate, flags=re.DOTALL)
    if m:
        candidate = m.group(1)
    repaired = json_repair.loads(candidate)
    if repaired in ("", None, [], {}):
        raise ValueError("Could not parse JSON from model response")
    return repaired


def parse_latex(text: str) -> str:
    block = extract_block(text, "latex") or extract_block(text, "tex")
    if block is None:
        if "\\documentclass" in text:
            start = text.index("\\documentclass")
            end = text.rfind("\\end{document}")
            if end != -1:
                return text[start:end + len("\\end{document}")]
        raise ValueError("No LaTeX block found in model response")
    return block


def parse_json_and_latex(text: str) -> dict:
    return {"json": parse_json(extract_block(text, "json") or "{}"),
            "latex": parse_latex(text)}


def parse_python(text: str) -> str:
    block = extract_block(text, "python")
    if block is None:
        raise ValueError("No python block found")
    return block


# --------------------------------------------------------------------------
# Attachments
# --------------------------------------------------------------------------

@dataclass
class Attachment:
    path: str

    @property
    def mime(self) -> str:
        m, _ = mimetypes.guess_type(self.path)
        return m or "application/octet-stream"

    def b64(self) -> str:
        with open(self.path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode()


# --------------------------------------------------------------------------
# Usage accounting
# --------------------------------------------------------------------------

@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_agent: dict = field(default_factory=dict)

    def add(self, agent: str, inp: int, out: int):
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        a = self.by_agent.setdefault(agent, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        a["calls"] += 1
        a["input_tokens"] += inp
        a["output_tokens"] += out


# --------------------------------------------------------------------------
# Main client
# --------------------------------------------------------------------------

class LLM:
    """Thin multi-provider client.

    ``api_keys`` may contain ``anthropic``, ``gemini``, ``openai``; missing keys
    fall back to environment variables (ANTHROPIC_API_KEY, GEMINI_API_KEY,
    OPENAI_API_KEY).
    """

    def __init__(self, model: str, api_keys: Optional[dict] = None,
                 max_tokens: int = 32000, usage: Optional[Usage] = None,
                 log: Callable[[str], None] = print):
        self.model = model
        self.api_keys = api_keys or {}
        self.max_tokens = max_tokens
        self.usage = usage or Usage()
        self.log = log
        self.provider = self._provider(model)
        self._client = None

    @staticmethod
    def _provider(model: str) -> str:
        m = model.lower()
        if m.startswith("mock"):
            return "mock"
        if m.startswith("claude"):
            return "anthropic"
        if m.startswith("gemini"):
            return "gemini"
        if m.startswith(("gpt", "o1", "o3", "o4")):
            return "openai"
        raise ValueError(f"Unknown model provider for '{model}'")

    # ---------------- client factories ----------------
    def _anthropic(self):
        if self._client is None:
            import anthropic
            key = self.api_keys.get("anthropic") or os.environ.get("ANTHROPIC_API_KEY")
            self._client = anthropic.Anthropic(api_key=key, max_retries=4)
        return self._client

    def _gemini(self):
        if self._client is None:
            from google import genai
            key = self.api_keys.get("gemini") or os.environ.get("GEMINI_API_KEY")
            if key:
                self._client = genai.Client(api_key=key)
            else:
                self._client = genai.Client(
                    vertexai=True,
                    project=os.environ.get("VERTEX_AI_PROJECT"),
                    location=os.environ.get("VERTEX_AI_LOCATION", "global"))
        return self._client

    def _openai(self):
        if self._client is None:
            import openai
            key = self.api_keys.get("openai") or os.environ.get("OPENAI_API_KEY")
            self._client = openai.OpenAI(api_key=key)
        return self._client

    # ---------------- public API ----------------
    def generate(self, prompt: str, system: str = "", attachments: Optional[list] = None,
                 temperature: float = 0.7, agent: str = "generic",
                 parser: Optional[Callable[[str], Any]] = None, retries: int = 3) -> Any:
        """Generate a completion; if ``parser`` is given, retry until it parses."""
        attachments = [a if isinstance(a, Attachment) else Attachment(a) for a in (attachments or [])]
        last_err = None
        for attempt in range(retries):
            try:
                text = self._call(prompt, system, attachments, temperature, agent)
                return parser(text) if parser else text
            except Exception as e:  # noqa: BLE001
                last_err = e
                self.log(f"   [llm:{agent}] attempt {attempt + 1}/{retries} failed: {e}")
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM call failed for agent '{agent}': {last_err}")

    def _call(self, prompt, system, attachments, temperature, agent) -> str:
        if self.provider == "mock":
            from postudio.mock_llm import mock_response
            text = mock_response(prompt, system, agent)
            self.usage.add(agent, len(prompt) // 4, len(text) // 4)
            return text
        if self.provider == "anthropic":
            return self._call_anthropic(prompt, system, attachments, temperature, agent)
        if self.provider == "gemini":
            return self._call_gemini(prompt, system, attachments, temperature, agent)
        return self._call_openai(prompt, system, attachments, temperature, agent)

    def _call_anthropic(self, prompt, system, attachments, temperature, agent) -> str:
        client = self._anthropic()
        content = []
        for a in attachments:
            if a.mime == "application/pdf":
                content.append({"type": "document", "source": {
                    "type": "base64", "media_type": "application/pdf", "data": a.b64()}})
            elif a.mime.startswith("image/"):
                content.append({"type": "image", "source": {
                    "type": "base64", "media_type": a.mime, "data": a.b64()}})
        content.append({"type": "text", "text": prompt})
        kwargs = dict(model=self.model, max_tokens=self.max_tokens,
                      messages=[{"role": "user", "content": content}])
        if system:
            kwargs["system"] = system
        kwargs["temperature"] = temperature
        # Long outputs (full LaTeX papers) require streaming.
        chunks = []
        with client.messages.stream(**kwargs) as stream:
            for t in stream.text_stream:
                chunks.append(t)
            final = stream.get_final_message()
        self.usage.add(agent, final.usage.input_tokens, final.usage.output_tokens)
        return "".join(chunks)

    def _call_gemini(self, prompt, system, attachments, temperature, agent) -> str:
        from google.genai import types
        client = self._gemini()
        parts = []
        for a in attachments:
            with open(a.path, "rb") as f:
                parts.append(types.Part.from_bytes(data=f.read(), mime_type=a.mime))
        parts.append(types.Part.from_text(text=prompt))
        cfg = types.GenerateContentConfig(temperature=temperature,
                                          system_instruction=system or None,
                                          max_output_tokens=min(self.max_tokens, 65536))
        resp = client.models.generate_content(model=self.model, contents=parts, config=cfg)
        um = getattr(resp, "usage_metadata", None)
        self.usage.add(agent, getattr(um, "prompt_token_count", 0) or 0,
                       getattr(um, "candidates_token_count", 0) or 0)
        return resp.text or ""

    def _call_openai(self, prompt, system, attachments, temperature, agent) -> str:
        client = self._openai()
        content = []
        for a in attachments:
            if a.mime.startswith("image/"):
                content.append({"type": "input_image",
                                "image_url": f"data:{a.mime};base64,{a.b64()}"})
            elif a.mime == "application/pdf":
                content.append({"type": "input_file", "filename": os.path.basename(a.path),
                                "file_data": f"data:application/pdf;base64,{a.b64()}"})
        content.append({"type": "input_text", "text": prompt})
        resp = client.responses.create(model=self.model, instructions=system or None,
                                       input=[{"role": "user", "content": content}])
        u = getattr(resp, "usage", None)
        self.usage.add(agent, getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0)
        return resp.output_text
