"""Article CRUD on note.com.

Endpoints (reverse-engineered from the editor's traffic, 2026-04):

- GET  /v3/notes/{key}                 — fetch single (returns numeric id + body)
- GET  /v2/note_list/contents          — list my articles (drafts + published)
- POST /v1/text_notes                  — create empty article (no body) → returns id, key
- POST /v1/text_notes/draft_save?id=…  — save draft body
- PUT  /v1/text_notes/{numeric_id}     — publish (uses `free_body`, hashtags ["#tag", …])
- DELETE /v1/notes/n/{key}             — delete draft
"""

from __future__ import annotations

import re
from typing import Any

from note_mcp.client import NoteAPIError, NoteClient
from note_mcp.embeds import find_embed_placeholders, resolve_embed_keys
from note_mcp.markdown import list_separator_candidates, markdown_to_note_html


def _is_key(article_id: str) -> bool:
    return article_id.startswith("n") and not article_id.isdigit()


async def _resolve_numeric_id(client: NoteClient, article_id: str) -> str:
    if article_id.isdigit():
        return article_id
    if not re.match(r"^n[a-z0-9]+$", article_id):
        raise NoteAPIError(0, "invalid article id format", article_id)
    response = await client.get(f"/v3/notes/{article_id}")
    data = response.get("data", {})
    numeric = data.get("id")
    if not numeric:
        raise NoteAPIError(0, "could not resolve numeric id", str(response)[:300])
    return str(numeric)


def _hashtags_for_draft(tags: list[str] | None) -> list[dict[str, Any]] | None:
    if not tags:
        return None
    return [{"hashtag": {"name": t.lstrip("#")}} for t in tags]


def _hashtags_for_publish(tags: list[str] | None) -> list[str] | None:
    if not tags:
        return None
    return [f"#{t.lstrip('#')}" for t in tags]


async def list_articles(
    *,
    status: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> dict[str, Any]:
    """status: "draft" | "published" | None"""
    params: dict[str, Any] = {"page": page}
    if status:
        params["publish_status"] = status

    async with NoteClient() as client:
        response = await client.get("/v2/note_list/contents", params=params)
    data = response.get("data", {})
    notes = data.get("notes", [])[:limit]
    return {
        "articles": [
            {
                "id": n.get("id"),
                "key": n.get("key"),
                "title": n.get("name"),
                "status": n.get("status"),
                "url": n.get("note_url"),
                "published_at": n.get("publish_at") or n.get("published_at"),
                "updated_at": n.get("updated_at"),
            }
            for n in notes
        ],
        "total": data.get("totalCount", len(notes)),
        "page": page,
        "has_more": not data.get("isLastPage", True),
    }


async def get_article(article_id: str) -> dict[str, Any]:
    if article_id.isdigit():
        raise NoteAPIError(0, "/v3/notes/ requires key format (n…)", article_id)
    async with NoteClient() as client:
        response = await client.get(f"/v3/notes/{article_id}")
    data = response.get("data", {})
    note_draft = data.get("note_draft") or {}
    return {
        "id": data.get("id"),
        "key": data.get("key"),
        "title": note_draft.get("name") or data.get("name"),
        "body_html": note_draft.get("body") or data.get("body") or "",
        "status": data.get("status"),
        "url": data.get("note_url"),
        "raw_data": data,
    }


async def create_draft(
    *,
    title: str,
    body_markdown: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    html_body = markdown_to_note_html(body_markdown)
    create_payload: dict[str, Any] = {
        "name": title,
        "index": False,
        "is_lead_form": False,
    }
    hashtags = _hashtags_for_draft(tags)
    if hashtags:
        create_payload["hashtags"] = hashtags

    async with NoteClient() as client:
        created = await client.post("/v1/text_notes", json=create_payload)
        data = created.get("data", {})
        article_id = data.get("id")
        article_key = data.get("key")
        if not article_id or not article_key:
            raise NoteAPIError(0, "create_draft: API returned no id/key", str(created)[:300])

    # Resolve embed keys (after we have an article_key) — only if there are placeholders
    if find_embed_placeholders(html_body):
        html_body = await resolve_embed_keys(html_body, str(article_key))

    async with NoteClient() as client:
        save_payload: dict[str, Any] = {
            "name": title,
            "body": html_body,
            "body_length": len(html_body),
            "index": False,
            "is_lead_form": False,
        }
        if hashtags:
            save_payload["hashtags"] = hashtags
        await client.post(
            f"/v1/text_notes/draft_save?id={article_id}&is_temp_saved=true",
            json=save_payload,
        )

    return {
        "id": str(article_id),
        "key": str(article_key),
        "title": title,
        "status": "draft",
    }


async def update_article(
    article_id: str,
    *,
    title: str,
    body_markdown: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    html_body = markdown_to_note_html(body_markdown)

    async with NoteClient() as client:
        numeric = await _resolve_numeric_id(client, article_id)

    # Resolve embed keys (only if placeholders exist)
    if find_embed_placeholders(html_body) and _is_key(article_id):
        html_body = await resolve_embed_keys(html_body, article_id)

    async with NoteClient() as client:
        payload: dict[str, Any] = {
            "name": title,
            "body": html_body,
            "body_length": len(html_body),
            "index": False,
            "is_lead_form": False,
        }
        hashtags = _hashtags_for_draft(tags)
        if hashtags:
            payload["hashtags"] = hashtags
        await client.post(
            f"/v1/text_notes/draft_save?id={numeric}&is_temp_saved=true",
            json=payload,
        )

    return {
        "id": numeric,
        "key": article_id if _is_key(article_id) else "",
        "title": title,
        "status": "draft",
    }


async def publish_article(
    article_key: str,
    *,
    tags: list[str] | None = None,
    magazine_keys: list[str] | None = None,
    circle_plan_keys: list[str] | None = None,
    price: int | None = None,
    separator_uuid: str | None = None,
    limited: bool | None = None,
    disable_comment: bool | None = None,
    title_override: str | None = None,
) -> dict[str, Any]:
    """Publish a draft. Use title_override to force-update the published title."""
    if article_key.isdigit():
        raise NoteAPIError(0, "publish_article requires key format (n…)", article_key)

    async with NoteClient() as client:
        article_response = await client.get(f"/v3/notes/{article_key}")
        article_data = article_response.get("data", {})
        numeric = str(article_data.get("id"))
        note_draft = article_data.get("note_draft") or {}
        article_title = title_override or note_draft.get("name") or article_data.get("name", "")
        article_body = note_draft.get("body") or article_data.get("body") or ""

        payload: dict[str, Any] = {
            "name": article_title,
            "free_body": article_body,
            "body_length": len(article_body),
            "status": "published",
            "index": False,
        }
        publish_tags = _hashtags_for_publish(tags)
        if publish_tags:
            payload["hashtags"] = publish_tags
        if magazine_keys is not None:
            payload["magazine_keys"] = list(magazine_keys)
        if circle_plan_keys is not None:
            payload["circle_permissions"] = (
                [{"kind": "circle_plan", "keys": list(circle_plan_keys)}]
                if circle_plan_keys
                else []
            )
        if price is not None:
            payload["price"] = price
        if separator_uuid is not None:
            payload["separator"] = separator_uuid
        if limited is not None:
            payload["limited"] = limited
        if disable_comment is not None:
            payload["disable_comment"] = disable_comment

        response = await client.put(f"/v1/text_notes/{numeric}", json=payload)

    data = response.get("data", {})
    if data.get("result") is False:
        raise NoteAPIError(0, "publish API returned result=false", str(response)[:300])
    return {
        "id": numeric,
        "key": article_key,
        "title": article_title,
        "status": "published",
        "url": f"https://note.com/{article_key}",
    }


async def get_separator_candidates(article_key: str) -> list[dict[str, str]]:
    article = await get_article(article_key)
    return list_separator_candidates(article["body_html"])


async def set_paid_settings(
    article_key: str,
    *,
    price: int | None = None,
    separator_uuid: str | None = None,
) -> dict[str, Any]:
    """Set price and/or separator on a draft (without publishing)."""
    if article_key.isdigit():
        raise NoteAPIError(0, "set_paid_settings requires key format (n…)", article_key)

    async with NoteClient() as client:
        response = await client.get(f"/v3/notes/{article_key}")
        data = response.get("data", {})
        numeric = str(data.get("id"))
        note_draft = data.get("note_draft") or {}
        title = note_draft.get("name") or data.get("name", "")
        body = note_draft.get("body") or data.get("body") or ""

        payload: dict[str, Any] = {
            "name": title,
            "body": body,
            "body_length": len(body),
            "index": False,
            "is_lead_form": False,
        }
        if price is not None:
            payload["price"] = price
        if separator_uuid is not None:
            payload["separator"] = separator_uuid
        await client.post(
            f"/v1/text_notes/draft_save?id={numeric}&is_temp_saved=true",
            json=payload,
        )

    return {
        "id": numeric,
        "key": article_key,
        "price": price,
        "separator_uuid": separator_uuid,
    }


async def delete_draft(article_key: str) -> dict[str, Any]:
    if article_key.isdigit():
        raise NoteAPIError(0, "delete_draft requires key format (n…)", article_key)
    async with NoteClient() as client:
        info = await client.get(f"/v3/notes/{article_key}")
        if info.get("data", {}).get("status") == "published":
            raise NoteAPIError(0, "cannot delete a published article", article_key)
        await client.delete(f"/v1/notes/n/{article_key}")
    return {"key": article_key, "deleted": True}


async def delete_all_drafts(*, confirm: bool = False) -> dict[str, Any]:
    """Bulk-delete all drafts. confirm=False returns a preview, confirm=True actually deletes."""
    drafts: list[dict[str, Any]] = []
    page = 1
    async with NoteClient() as client:
        while page <= 100:
            response = await client.get(
                "/v2/note_list/contents",
                params={"publish_status": "draft", "page": page},
            )
            data = response.get("data", {})
            notes = data.get("notes", [])
            if not notes:
                break
            for n in notes:
                if n.get("key"):
                    drafts.append(
                        {"key": n["key"], "title": n.get("name", ""), "id": n.get("id")}
                    )
            if data.get("isLastPage"):
                break
            page += 1

    if not confirm:
        return {
            "preview": True,
            "total": len(drafts),
            "drafts": drafts[:30],
            "message": f"{len(drafts)} 件の下書きを削除します。confirm=True で実行。",
        }

    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    async with NoteClient() as client:
        for d in drafts:
            try:
                await client.delete(f"/v1/notes/n/{d['key']}")
                deleted.append(d["key"])
            except Exception as exc:
                failed.append({"key": d["key"], "error": str(exc)[:200]})

    return {
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted_keys": deleted,
        "failed": failed,
    }


async def insert_body_image(
    article_id: str,
    image_url: str,
    *,
    caption: str = "",
    width: int = 620,
    height: int = 457,
) -> dict[str, Any]:
    """Append an image (already uploaded → URL) to the article body and save.

    Use after `upload_body_image` returns a URL — this puts a <figure> at the
    end of the existing body. For more precise positioning, edit the markdown
    yourself and call `update_article` instead.
    """
    import html as html_module

    if article_id.isdigit():
        raise NoteAPIError(0, "insert_body_image requires key format (n…)", article_id)

    article = await get_article(article_id)
    title = article["title"]
    existing_html = article["body_html"]

    fig_uuid = re.sub(r"[^0-9a-f-]", "", "")  # placeholder, regenerate below
    import uuid as _uuid

    fig_uuid = str(_uuid.uuid4())
    img_uuid = str(_uuid.uuid4())
    safe_caption = html_module.escape(caption)
    safe_url = html_module.escape(image_url)
    figure_html = (
        f'<figure name="{fig_uuid}" id="{fig_uuid}">'
        f'<img src="{safe_url}" alt="" width="{width}" height="{height}" '
        f'name="{img_uuid}" id="{img_uuid}" '
        f'contenteditable="false" draggable="false">'
        f"<figcaption>{safe_caption}</figcaption></figure>"
    )
    new_html = existing_html + figure_html

    async with NoteClient() as client:
        numeric = await _resolve_numeric_id(client, article_id)
        await client.post(
            f"/v1/text_notes/draft_save?id={numeric}&is_temp_saved=true",
            json={
                "name": title,
                "body": new_html,
                "body_length": len(new_html),
                "index": False,
                "is_lead_form": False,
            },
        )

    return {
        "id": numeric,
        "key": article_id,
        "image_url": image_url,
        "appended": True,
    }


async def get_preview_access_token(article_key: str) -> str:
    """Issue a preview access token so the draft can be viewed without editor login."""
    if article_key.isdigit():
        raise NoteAPIError(0, "preview requires key format (n…)", article_key)
    async with NoteClient() as client:
        response = await client.post(
            f"/v2/notes/{article_key}/access_tokens",
            json={"key": article_key},
        )
    token = response.get("data", {}).get("preview_access_token")
    if not token:
        raise NoteAPIError(0, "preview token not returned", str(response)[:300])
    return str(token)


def build_preview_url(article_key: str, token: str) -> str:
    return f"https://note.com/preview/{article_key}?prev_access_key={token}"


async def get_preview_url(article_key: str) -> str:
    token = await get_preview_access_token(article_key)
    return build_preview_url(article_key, token)


async def get_preview_html(article_key: str) -> str:
    """Fetch the rendered preview page HTML."""
    import httpx

    url = await get_preview_url(article_key)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
    return response.text


async def create_from_file(file_path: str, *, tags_override: list[str] | None = None) -> dict[str, Any]:
    """Create a draft from a Markdown file.

    Optional YAML frontmatter is supported:
        ---
        title: 記事タイトル
        tags: [tagA, tagB]
        ---
        本文…
    """
    import yaml

    raw = open(file_path, encoding="utf-8").read()
    title = ""
    tags: list[str] | None = None
    body = raw

    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end > 0:
            try:
                meta = yaml.safe_load(raw[4:end]) or {}
                title = str(meta.get("title") or "").strip()
                if isinstance(meta.get("tags"), list):
                    tags = [str(t) for t in meta["tags"]]
                body = raw[end + 5 :]
            except yaml.YAMLError:
                pass

    if not title:
        # Fall back to first H1
        m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = m.group(1).strip() if m else "Untitled"

    if tags_override is not None:
        tags = tags_override

    return await create_draft(title=title, body_markdown=body, tags=tags)
