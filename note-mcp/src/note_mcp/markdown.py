"""Markdown → note.com HTML conversion.

note.com's editor stores rich HTML where every block (h1-h6, p, ul, ol, hr,
figure, code, div) carries `name="UUID" id="UUID"`. The `separator` field
on a paid article references one of these UUIDs to mark the paywall start.

This converter:
1. Runs CommonMark via markdown-it-py.
2. Adds UUIDs to block elements.
3. Converts <p><img></p> into note's <figure><img></figure> shape.
4. Cleans up <pre><code class="language-x"> into note's preferred <pre> form.
5. Replaces standalone YouTube/Twitter/note URLs with <figure> embed
   placeholders (real server keys are filled in by embeds.resolve_embed_keys
   after the draft has an article_key).
"""

from __future__ import annotations

import re
import uuid

from markdown_it import MarkdownIt

_BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "hr", "code", "div")
_BLOCK_OPEN = re.compile(
    r"<(" + "|".join(_BLOCK_TAGS) + r")(\s[^>]*)?>",
    re.IGNORECASE,
)
_PRE_BLOCK = re.compile(r"<pre([^>]*)>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_IMG_IN_P = re.compile(
    r'<p>\s*<img\s+src="([^"]+)"\s+alt="([^"]*)"(?:\s+title="([^"]*)")?\s*/?\s*>\s*</p>',
    re.IGNORECASE,
)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _add_uuid_to_block(match: re.Match[str]) -> str:
    tag = match.group(1)
    attrs = match.group(2) or ""
    if 'name="' in attrs:
        return match.group(0)
    uid = _new_uuid()
    return f'<{tag}{attrs} name="{uid}" id="{uid}">'


def _wrap_pre(match: re.Match[str]) -> str:
    attrs = match.group(1) or ""
    inner = match.group(2)
    uid = _new_uuid()
    code_uid = _new_uuid()
    # Strip language-* class on inner code, note doesn't use it
    cleaned = re.sub(r' class="language-[^"]*"', "", inner)
    return f'<pre{attrs} name="{uid}" id="{uid}"><code name="{code_uid}" id="{code_uid}">{_inner_code(cleaned)}</code></pre>'


def _inner_code(s: str) -> str:
    # If markdown-it nested <code>...</code> inside <pre>, strip the outer code tag
    m = re.match(r"\s*<code[^>]*>(.*)</code>\s*$", s, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else s


def _img_to_figure(match: re.Match[str]) -> str:
    src = match.group(1)
    alt = match.group(2)
    fig_uid = _new_uuid()
    img_uid = _new_uuid()
    return (
        f'<figure name="{fig_uid}" id="{fig_uid}">'
        f'<img src="{src}" alt="{alt}" name="{img_uid}" id="{img_uid}"/>'
        f"</figure>"
    )


def markdown_to_note_html(content: str) -> str:
    """Convert Markdown into the HTML shape note.com's API expects."""
    from note_mcp.embeds import inject_embed_placeholders

    md = MarkdownIt("commonmark", {"breaks": True, "html": True}).enable("table")
    html = md.render(content)
    # 1. Replace <p><img></p> → <figure>
    html = _IMG_IN_P.sub(_img_to_figure, html)
    # 2. Wrap <pre> with UUIDs
    html = _PRE_BLOCK.sub(_wrap_pre, html)
    # 3. Replace <p>URL</p> with embed <figure> placeholders for known services
    html = inject_embed_placeholders(html)
    # 4. Add UUIDs to remaining block tags
    html = _BLOCK_OPEN.sub(_add_uuid_to_block, html)
    return html


_BLOCK_UUID_PATTERN = re.compile(
    r'<(h2|h3|h4|p)\s[^>]*\bname="([0-9a-f-]{36})"[^>]*>(.*?)</\1>',
    re.DOTALL | re.IGNORECASE,
)


def list_separator_candidates(html: str) -> list[dict[str, str]]:
    """Return a list of `{uuid, level, text}` blocks suitable for paid separator selection."""
    out: list[dict[str, str]] = []
    for m in _BLOCK_UUID_PATTERN.finditer(html):
        level = m.group(1).lower()
        uid = m.group(2)
        text = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        if not text:
            continue
        out.append({"uuid": uid, "level": level, "text": text[:80]})
    return out
