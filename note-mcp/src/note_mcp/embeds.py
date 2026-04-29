"""Embed handling for YouTube / Twitter / note article URLs.

In note.com's HTML, an embed looks like:

    <figure embedded-service="youtube" embedded-key="SERVER_KEY"
            name="UUID" id="UUID" data-original-link="https://...">
      <iframe src="https://youtube.com/embed/..." ...></iframe>
    </figure>

Flow:
1. Detect standalone URLs in markdown lines (one URL on a line by itself).
2. After markdown→HTML conversion, swap the resulting <p>URL</p> with our
   <figure> placeholder containing a *random* embedded-key.
3. After the draft is created (so we have an article key), call
   /v2/embed_by_external_api?url=<URL>&note_key=<ARTICLE_KEY> to get the
   real server-registered key, then replace the random one.

The two-step flow is necessary because note's API rejects random keys at
publish time but accepts them at draft_save time.
"""

from __future__ import annotations

import re
import uuid


# Service detection — order matters (most specific first)
_YOUTUBE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]+)",
    re.IGNORECASE,
)
_TWITTER = re.compile(
    r"^https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/(\d+)",
    re.IGNORECASE,
)
_NOTE_ARTICLE = re.compile(
    r"^https?://note\.com/[\w-]+/n/(n[a-z0-9]+)",
    re.IGNORECASE,
)


def detect_embed_service(url: str) -> str | None:
    if _YOUTUBE.match(url):
        return "youtube"
    if _TWITTER.match(url):
        return "twitter"
    if _NOTE_ARTICLE.match(url):
        return "note"
    return None


# After markdown→HTML, paragraphs containing only a URL look like:
#   <p>https://youtube.com/watch?v=xxx</p>
# (UUIDs may have been added already; handle both shapes)
_URL_PARAGRAPH = re.compile(
    r'<p(?:\s+name="[^"]+"\s+id="[^"]+")?>\s*(https?://\S+?)\s*</p>',
    re.IGNORECASE,
)


def _build_embed_figure(url: str, service: str) -> str:
    """Build a <figure> placeholder. embedded-key starts as a random UUID;
    the real server key is patched in after the draft exists.
    """
    fig_uid = str(uuid.uuid4())
    placeholder_key = uuid.uuid4().hex[:24]
    iframe = _build_iframe(url, service)
    return (
        f'<figure name="{fig_uid}" id="{fig_uid}" '
        f'embedded-service="{service}" embedded-key="{placeholder_key}" '
        f'data-original-link="{url}" contenteditable="false">'
        f"{iframe}"
        f"</figure>"
    )


def _build_iframe(url: str, service: str) -> str:
    if service == "youtube":
        m = _YOUTUBE.match(url)
        vid = m.group(1) if m else ""
        return (
            f'<iframe src="https://www.youtube.com/embed/{vid}" '
            f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; '
            f'encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'
        )
    if service == "twitter":
        return (
            f'<iframe src="{url}" frameborder="0" '
            f'sandbox="allow-scripts allow-same-origin allow-popups"></iframe>'
        )
    if service == "note":
        return f'<iframe src="{url}" frameborder="0"></iframe>'
    return f'<iframe src="{url}" frameborder="0"></iframe>'


def inject_embed_placeholders(html: str) -> str:
    """Replace <p>URL</p> blocks with <figure> embed placeholders for known services."""

    def _repl(match: re.Match[str]) -> str:
        url = match.group(1).strip()
        service = detect_embed_service(url)
        if not service:
            return match.group(0)
        return _build_embed_figure(url, service)

    return _URL_PARAGRAPH.sub(_repl, html)


_EMBED_FIGURE = re.compile(
    r'(<figure\s+[^>]*?embedded-service="(?P<service>[^"]+)"\s+'
    r'embedded-key=")(?P<key>[^"]+)("[^>]*?'
    r'data-original-link="(?P<url>[^"]+)"[^>]*>.*?</figure>)',
    re.DOTALL,
)


def find_embed_placeholders(html: str) -> list[dict[str, str]]:
    """Return embed positions that still carry placeholder keys."""
    out: list[dict[str, str]] = []
    for m in _EMBED_FIGURE.finditer(html):
        out.append({"url": m.group("url"), "key": m.group("key"), "service": m.group("service")})
    return out


def replace_embed_key(html: str, original_url: str, new_key: str) -> str:
    """Replace the embedded-key for the figure pointing at original_url."""

    def _repl(match: re.Match[str]) -> str:
        if match.group("url") != original_url:
            return match.group(0)
        return f'{match.group(1)}{new_key}{match.group(4)}'

    return _EMBED_FIGURE.sub(_repl, html)


async def resolve_embed_keys(html: str, article_key: str) -> str:
    """Resolve placeholder embed keys against /v2/embed_by_external_api.

    Called after the draft is created. For each embed placeholder, fetch the
    real server-registered key and patch it in.
    """
    placeholders = find_embed_placeholders(html)
    if not placeholders:
        return html

    # Late import to avoid circular dependency (client → markdown → embeds → client)
    from note_mcp.client import NoteClient

    async with NoteClient() as client:
        for ph in placeholders:
            try:
                response = await client.get(
                    "/v2/embed_by_external_api",
                    params={"url": ph["url"], "note_key": article_key},
                )
                data = response.get("data", {})
                server_key = data.get("key") or data.get("embed_key")
                if server_key:
                    html = replace_embed_key(html, ph["url"], str(server_key))
            except Exception:
                # Embed resolution is best-effort. Leave the placeholder if it fails;
                # the embed may still render but not be tracked server-side.
                continue
    return html
