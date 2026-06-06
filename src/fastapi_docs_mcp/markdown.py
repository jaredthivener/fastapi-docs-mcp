"""Markdown pipeline: fetch raw docs, resolve code includes, clean MkDocs syntax.

This is the preferred (token-efficient) content path. It turns FastAPI's raw
markdown — with its ``{* docs_src/... *}`` include directives, ``///`` admonitions,
``{ #anchor }`` heading suffixes, and ``termy`` console HTML — into clean markdown.
"""

from __future__ import annotations

import asyncio
import re

from . import html as html_fallback
from . import http
from .config import (
    DOCS_RAW_BASE,
    MAX_CONTENT_LENGTH,
    MAX_INCLUDES,
    REPO_RAW_ROOT,
)

# --- Directive / syntax patterns -------------------------------------------
_INCLUDE_RE = re.compile(
    r"\{\*\s*(?P<path>\S+?)(?P<args>(?:\s+[a-zA-Z]+\[[^\]]*\])*)\s*\*\}"
)
_LEGACY_RE = re.compile(r"\{!\s*(?P<path>[^!\s]+)\s*!\}")
_LN_RE = re.compile(r"ln\[(\d+):(\d+)\]")
_LEFTOVER_INCLUDE_RE = re.compile(r"\{\*.*?\*\}|\{!.*?!\}", re.DOTALL)

_FENCE_LINE_RE = re.compile(r"^(`{3,})(.*)$")
_ANCHOR_RE = re.compile(r"\s*\{\s*#[\w-]+\s*\}\s*$", re.MULTILINE)
_ADMONITION_OPEN_RE = re.compile(
    r'^/{3,4}\s*(\w+)(?:\s*\|\s*"?([^"\n]*?)"?)?\s*$', re.MULTILINE
)
_ADMONITION_CLOSE_RE = re.compile(r"^/{3,4}\s*$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")

_PY_LANGS = {"python", "py"}
_CONSOLE_LANGS = {"console", "bash", "sh", "shell"}
_OTHER_BLOCK_MAX = 600  # cap json/toml/text dumps (schemas, configs)


# --- URL resolution ---------------------------------------------------------
def md_url_candidates(path: str) -> list[str]:
    """Candidate raw-markdown URLs for a doc path (first that exists wins)."""
    p = path.strip().strip("/")
    if not p:
        return [f"{DOCS_RAW_BASE}/index.md"]
    return [f"{DOCS_RAW_BASE}/{p}.md", f"{DOCS_RAW_BASE}/{p}/index.md"]


async def fetch_markdown(path: str) -> str | None:
    """Fetch raw markdown for a doc path, trying section-index fallback."""
    for url in md_url_candidates(path):
        md = await http.fetch(url)
        if md:
            return md
    return None


# --- Include resolution -----------------------------------------------------
def _include_url(ref: str) -> str | None:
    """Map an include ref to a raw URL by anchoring on the repo-root docs_src/."""
    idx = ref.find("docs_src/")
    if idx == -1:
        return None
    return f"{REPO_RAW_ROOT}/{ref[idx:]}"


def _slice_lines(code: str, args: str) -> str:
    """Honor an ``ln[a:b]`` directive (1-based, inclusive) if present."""
    m = _LN_RE.search(args)
    if not m:
        return code
    start, end = int(m.group(1)), int(m.group(2))
    lines = code.splitlines()
    return "\n".join(lines[max(start - 1, 0) : end])


def _directives(md: str) -> list[tuple[int, int, str, str]]:
    """Collect (start, end, ref, args) for every include directive, in order."""
    found: list[tuple[int, int, str, str]] = [
        (m.start(), m.end(), m.group("path"), m.group("args") or "")
        for m in _INCLUDE_RE.finditer(md)
    ]
    found += [
        (m.start(), m.end(), m.group("path"), "") for m in _LEGACY_RE.finditer(md)
    ]
    found.sort()
    return found


async def resolve_includes(md: str) -> str:
    """Replace ``{* docs_src/... *}`` directives with the referenced code, inlined."""
    directives = _directives(md)[:MAX_INCLUDES]
    if not directives:
        return md

    urls = [_include_url(ref) for _, _, ref, _ in directives]
    codes = await asyncio.gather(*(http.fetch(u) if u else _none() for u in urls))

    parts: list[str] = []
    last = 0
    for (start, end, ref, args), code in zip(directives, codes, strict=True):
        parts.append(md[last:start])
        if code is None:
            parts.append(f"```python\n# (example unavailable: {ref})\n```")
        else:
            snippet = _slice_lines(code, args).strip("\n")
            parts.append(f"```python\n{snippet}\n```")
        last = end
    parts.append(md[last:])
    return "".join(parts)


async def _none() -> str | None:
    return None


# --- Cleanup ----------------------------------------------------------------
def _split_blocks(md: str) -> list[tuple[str | None, str]]:
    """Split markdown into ordered (kind, content) blocks.

    ``kind`` is ``None`` for prose, otherwise the (lower-cased) fence language
    (``""`` for an untagged fence). A line-state machine is used rather than a
    regex so prose/code spans never get mis-paired — which would both leak
    MkDocs syntax into prose and risk mangling code.
    """
    blocks: list[tuple[str | None, str]] = []
    text: list[str] = []
    lines = md.split("\n")
    i, n = 0, len(lines)

    while i < n:
        fence = _FENCE_LINE_RE.match(lines[i])
        if fence:
            ticks = fence.group(1)
            lang = (fence.group(2).strip().split() or [""])[0].lower()
            body: list[str] = []
            i += 1
            while i < n and lines[i].strip() != ticks:
                body.append(lines[i])
                i += 1
            i += 1  # consume closing fence (or fall off the end)
            if text:
                blocks.append((None, "\n".join(text)))
                text = []
            blocks.append((lang, "\n".join(body)))
        else:
            text.append(lines[i])
            i += 1

    if text:
        blocks.append((None, "\n".join(text)))
    return blocks


def _clean_text_segment(text: str) -> str:
    text = _ADMONITION_OPEN_RE.sub(
        lambda m: f"**{m.group(2) or m.group(1).title()}**", text
    )
    text = _ADMONITION_CLOSE_RE.sub("", text)
    text = _LEFTOVER_INCLUDE_RE.sub("", text)  # over-cap / unresolvable directives
    text = _IMAGE_RE.sub("", text)  # ![alt](url) — screenshots, zero value to an LLM
    text = _LINK_RE.sub(r"\1", text)  # [text](url) -> text; drop URL token noise
    text = _HTML_TAG_RE.sub("", text)  # inline html: <abbr>, <a>, <img>, ...
    return text


def _render_code_block(lang: str, body: str) -> str | None:
    """Render a fenced block, dropping/condensing low-value content."""
    if lang in _PY_LANGS:
        return f"```python\n{body}\n```"
    if lang in _CONSOLE_LANGS:
        # Terminal blocks are mostly low-value log spew. Keep only the
        # actionable command lines ($ ...); drop the output entirely.
        cleaned = html_fallback.decode_html_entities(_HTML_TAG_RE.sub("", body))
        commands = [
            ln.rstrip() for ln in cleaned.splitlines() if ln.lstrip().startswith("$")
        ]
        return "```console\n" + "\n".join(commands) + "\n```" if commands else None
    # Other langs (json/toml/text): keep, but cap schema/config dumps.
    cleaned = _HTML_TAG_RE.sub("", body)
    if len(cleaned) > _OTHER_BLOCK_MAX:
        cleaned = cleaned[:_OTHER_BLOCK_MAX].rstrip() + "\n# ... (truncated)"
    fence = f"```{lang}\n" if lang else "```\n"
    return f"{fence}{cleaned}\n```"


def clean_mkdocs(md: str) -> str:
    """Strip MkDocs-specific syntax and HTML noise, preserving code fences."""
    md = _ANCHOR_RE.sub("", md)  # heading anchors live only at line ends

    out: list[str] = []
    for kind, content in _split_blocks(md):
        if kind is None:
            out.append(_clean_text_segment(content))
        else:
            rendered = _render_code_block(kind, content)
            if rendered is not None:
                out.append(rendered)

    result = "\n".join(out)
    result = re.sub(r"[ \t]+\n", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def extract_python_blocks(md: str) -> list[str]:
    """Return the Python code fences from (include-resolved) markdown."""
    blocks: list[str] = []
    for kind, content in _split_blocks(md):
        if kind in _PY_LANGS:
            code = _HTML_TAG_RE.sub("", content).strip()
            if len(code) > 20:
                blocks.append(code)
    return blocks


def truncate_content(content: str, max_length: int = MAX_CONTENT_LENGTH) -> str:
    """Truncate to ``max_length`` chars, preferring a paragraph boundary."""
    if len(content) <= max_length:
        return content

    truncated = content[:max_length]
    last_break = truncated.rfind("\n\n")
    if last_break > max_length * 0.8:
        truncated = truncated[:last_break]
    return f"{truncated}\n\n... [Content truncated. Visit the URL for full content.]"


# --- High-level orchestration ----------------------------------------------
async def to_clean_markdown(path: str) -> str | None:
    """Full markdown path: fetch → resolve includes → clean. ``None`` if absent."""
    md = await fetch_markdown(path)
    if not md:
        return None
    md = await resolve_includes(md)
    cleaned = clean_mkdocs(md)
    return cleaned or None
