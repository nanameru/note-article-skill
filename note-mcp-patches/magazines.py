"""Magazine operations for note.com API.

Provides read-only listing of the authenticated user's own magazines.

Note: as of 2026-04 the add-note-to-magazine endpoint has not been identified
through reverse-engineering of the public bundles. Magazine assignment must be
done manually via note.com's web editor.
"""

from __future__ import annotations

import logging
from typing import Any

from note_mcp.api.client import NoteAPIClient
from note_mcp.models import ErrorCode, NoteAPIError, Session

logger = logging.getLogger(__name__)


async def list_my_magazines(
    session: Session,
    username: str | None = None,
) -> list[dict[str, Any]]:
    """List the authenticated user's own magazines.

    Uses `/v2/creators/{username}/contents?kind=magazine`. Unlike
    `/v1/my/magazines`, this endpoint returns BOTH `m*` and `md*` prefixed
    magazines (i.e. all kinds the user owns).

    Args:
        session: Authenticated session
        username: note.com username. If None, uses the username stored on the
            session (set by `note_login` or `note_set_username`).

    Returns:
        List of magazine dicts. Each dict includes (subset):
            - id (int)
            - key (str, e.g. "m755534d40888")
            - name (str)
            - price (int) — 0 for free magazines
            - status (str) — "public" / "private" / etc
            - isSubscribable (bool) — true if monthly subscription is enabled
            - isAuthor (bool) — true if the user owns this magazine
            - magazine_url (str, when computable)
    """
    target_username = username or getattr(session, "username", None)
    if not target_username:
        raise NoteAPIError(
            code=ErrorCode.INVALID_INPUT,
            message=(
                "username is required to list magazines. "
                "Pass it explicitly or call note_set_username first."
            ),
        )

    path = f"/v2/creators/{target_username}/contents"
    async with NoteAPIClient(session) as client:
        response = await client.get(path, params={"kind": "magazine"})

    data = response.get("data", {}) or {}
    contents = data.get("contents", []) or []
    return [m for m in contents if isinstance(m, dict)]


async def list_circle_plans(
    session: Session,
) -> list[dict[str, Any]]:
    """List the user's membership/circle plans (月額メンバーシッププラン).

    Uses `/v3/memberships/magazines/connectable_plans`. These are the plans
    that can be attached to a published article via the `circle_permissions`
    field on the publish endpoint.

    Returns:
        List of circle plan dicts. Each entry typically includes:
            - key (str, e.g. "458a7b74051c") — the plan key used in
              `circle_permissions`
            - name (str) — plan display name
            - price (int) — monthly price in JPY
            - start_at, end_at (ISO timestamps)
    """
    async with NoteAPIClient(session) as client:
        response = await client.get("/v3/memberships/magazines/connectable_plans")

    data = response.get("data", [])
    if isinstance(data, dict):
        # Older shape: data.plans
        data = data.get("plans", []) or []
    return [p for p in data if isinstance(p, dict)]
