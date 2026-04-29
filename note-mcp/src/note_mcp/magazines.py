"""Magazines + membership (circle) plans."""

from __future__ import annotations

from typing import Any

from note_mcp import session as session_store
from note_mcp.client import NoteAPIError, NoteClient


async def list_my_magazines() -> list[dict[str, Any]]:
    """Returns magazines (including m* prefixed ones).

    If username isn't cached, hit the API to discover it first — this is
    why the old MCP failed: it depended on DOM scraping for username and
    silently fell back to "username unknown" if scraping failed.
    """
    saved = session_store.load_session() or {}
    username = saved.get("username")
    if not username:
        from note_mcp.whoami import refresh_username_in_session

        username = await refresh_username_in_session()
    if not username:
        raise NoteAPIError(
            0,
            "username could not be determined via API. Try note_login again.",
            "",
        )

    async with NoteClient() as client:
        response = await client.get(
            f"/v2/creators/{username}/contents",
            params={"kind": "magazine", "page": 1},
        )
    data = response.get("data", {})
    contents = data.get("contents", []) or data.get("magazines", []) or data.get("notes", [])
    return [
        {
            "key": item.get("key") or item.get("id"),
            "name": item.get("name") or item.get("title"),
            "url": item.get("note_url") or item.get("url"),
            "kind": item.get("kind"),
        }
        for item in contents
    ]


async def list_circle_plans() -> list[dict[str, Any]]:
    """Returns the user's connectable membership plans."""
    async with NoteClient() as client:
        response = await client.get("/v3/memberships/magazines/connectable_plans")
    data = response.get("data", {})
    plans = data.get("plans") or data.get("connectable_plans") or []
    return [
        {
            "key": p.get("key") or p.get("id"),
            "name": p.get("name"),
            "price": p.get("price"),
            "circle_id": p.get("circle_id"),
            "magazine_key": p.get("magazine_key"),
        }
        for p in plans
    ]
