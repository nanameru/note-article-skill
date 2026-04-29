"""API-based current-user lookup.

Replaces DOM scraping for username retrieval. note.com offers several
authenticated endpoints that return the current user's id and urlname
in their response body. We try them in order and cache the result.

This is also the basis for `note_check_auth` — if the API call returns
401 / no user, we know the cookie is dead regardless of what's in the file.
"""

from __future__ import annotations

import logging
from typing import Any

from note_mcp import session as session_store
from note_mcp.client import NoteAPIError, NoteClient

logger = logging.getLogger(__name__)


# Endpoints to try, in order of preference. Each returns user info on success.
# Discovered by reverse-engineering the editor's startup traffic — these are
# the calls note.com itself makes on first page load to identify the user.
WHOAMI_ENDPOINTS = (
    "/v3/notifications/unread_count",  # tiny payload, returns user_key in some shapes
    "/v1/stats/pv",                     # returns user object alongside stats
    "/v2/note_list/contents",           # always returns notes for the auth'd user
)


def _extract_user_info(response: dict[str, Any]) -> dict[str, Any]:
    """Walk the response looking for {urlname, id} or {key, name} patterns."""
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        return {}

    # Direct shapes (varies by endpoint)
    candidates: list[dict[str, Any]] = []
    for key in ("user", "current_user", "creator", "owner"):
        v = data.get(key)
        if isinstance(v, dict):
            candidates.append(v)
    if data.get("urlname") or data.get("user_key"):
        candidates.append(data)

    # Notes endpoint returns notes[].user
    notes = data.get("notes")
    if isinstance(notes, list) and notes:
        first = notes[0]
        if isinstance(first, dict):
            user = first.get("user")
            if isinstance(user, dict):
                candidates.append(user)

    for c in candidates:
        urlname = c.get("urlname") or c.get("name") or c.get("user_urlname")
        user_id = c.get("id") or c.get("user_id") or c.get("key")
        if urlname:
            return {"urlname": str(urlname), "user_id": str(user_id or "")}

    return {}


async def fetch_current_user() -> dict[str, Any]:
    """Hit the API to get the current user. Raises if not authenticated."""
    last_error: Exception | None = None
    async with NoteClient() as client:
        for endpoint in WHOAMI_ENDPOINTS:
            try:
                response = await client._request("GET", endpoint)
                if response.status_code == 401:
                    raise NoteAPIError(401, "session is dead", "")
                if not response.is_success:
                    last_error = NoteAPIError(response.status_code, "", response.text[:200])
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    continue
                info = _extract_user_info(payload)
                if info.get("urlname"):
                    return info
            except NoteAPIError as exc:
                if exc.status == 401:
                    raise
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                continue

    raise NoteAPIError(0, f"could not identify current user via API: {last_error}", "")


async def refresh_username_in_session() -> str:
    """Look up the current username via API and persist it. Returns the username."""
    info = await fetch_current_user()
    saved = session_store.load_session() or {}
    if info.get("urlname"):
        saved["username"] = info["urlname"]
    if info.get("user_id"):
        saved["user_id"] = info["user_id"]
    session_store.save_session(saved)
    return info.get("urlname", "")


async def verify_auth() -> dict[str, Any]:
    """Active auth check — returns user info if valid, raises if not.

    Use this for note_check_auth. Unlike has_session() (which only checks
    file existence), this hits the API and is authoritative.
    """
    info = await fetch_current_user()
    return {"authenticated": True, **info}
