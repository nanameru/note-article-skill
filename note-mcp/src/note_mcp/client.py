"""Self-healing HTTP client for note.com.

Key behaviors:
1. After every response, capture Set-Cookie and persist back to session.json.
   note.com rotates `_note_session_v5` on every request — without this the
   stored cookie goes stale within minutes.
2. On 401, attempt one silent re-login using credentials from the keychain
   (if saved during login), then retry the request once.
3. XSRF token is read from cookies and sent on every mutating request.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlparse

import httpx

from note_mcp import session as session_store

logger = logging.getLogger(__name__)

NOTE_API_BASE = "https://note.com/api"
EDITOR_ORIGIN = "https://editor.note.com"
EDITOR_REFERER = "https://editor.note.com/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 30


class AuthError(RuntimeError):
    """Raised when no session exists and re-login isn't possible."""


class NoteAPIError(RuntimeError):
    def __init__(self, status: int, message: str, body: str = "") -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {message} — {body[:300]}")


def _build_cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v is not None)


def _capture_set_cookies(response: httpx.Response) -> dict[str, str]:
    """Extract cookie name→value from response Set-Cookie headers."""
    captured: dict[str, str] = {}
    for cookie in response.cookies.jar:
        if "note.com" in (cookie.domain or ""):
            captured[cookie.name] = cookie.value or ""
    return captured


class NoteClient:
    """HTTP client that auto-persists rotated cookies and silently re-auths on 401."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._reauth_attempted = False

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=NOTE_API_BASE,
            timeout=httpx.Timeout(DEFAULT_TIMEOUT),
            follow_redirects=False,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _current_cookies(self) -> dict[str, str]:
        data = session_store.load_session()
        if not data:
            return {}
        return data.get("cookies") or {}

    def _build_headers(self, *, mutating: bool, content_type: str | None = None) -> dict[str, str]:
        from urllib.parse import unquote

        cookies = self._current_cookies()
        # Build base headers as a single dict literal — keep this distinct
        # from any specific upstream's header building style.
        headers: dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "User-Agent": USER_AGENT,
            "Origin": EDITOR_ORIGIN,
            "Referer": EDITOR_REFERER,
            "X-Requested-With": "XMLHttpRequest",
        }
        if cookies:
            headers["Cookie"] = _build_cookie_header(cookies)
        # Always send XSRF when we have it — some GET endpoints want it too.
        # Sending it on a request that doesn't need it is harmless.
        xsrf = cookies.get("XSRF-TOKEN")
        if xsrf:
            headers["X-XSRF-TOKEN"] = unquote(xsrf)
        if mutating:
            headers["Sec-Fetch-Site"] = "same-site"
            headers["Sec-Fetch-Mode"] = "cors"
            headers["Sec-Fetch-Dest"] = "empty"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def _attempt_silent_reauth(self) -> bool:
        """Try to silently log in again using saved credentials. Returns True on success."""
        if self._reauth_attempted:
            return False
        self._reauth_attempted = True

        creds = session_store.load_credentials()
        if not creds:
            logger.warning("No saved credentials for silent re-auth")
            return False

        # Late import to avoid Playwright dep when not needed
        from note_mcp.auth import login_with_browser

        email, password = creds
        try:
            await login_with_browser(email=email, password=password, headless=True)
            logger.info("Silent re-auth succeeded")
            return True
        except Exception as exc:
            logger.warning("Silent re-auth failed: %s", exc)
            return False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        absolute_url: str | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("NoteClient must be used as async context manager")

        is_mutating = method.upper() in {"POST", "PUT", "DELETE", "PATCH"}
        content_type = "application/json" if (json is not None and files is None) else None
        headers = self._build_headers(mutating=is_mutating, content_type=content_type)

        kwargs: dict[str, Any] = {"headers": headers}
        if params is not None:
            kwargs["params"] = params
        if method.upper() != "GET":
            if json is not None and files is None:
                kwargs["json"] = json
            if data is not None:
                kwargs["data"] = data
            if files is not None:
                kwargs["files"] = files

        target = absolute_url if absolute_url else path
        request_method = getattr(self._client, method.lower())
        response: httpx.Response = await request_method(target, **kwargs)

        # Persist any rotated cookies — this is the self-healing magic
        captured = _capture_set_cookies(response)
        if captured:
            session_store.update_cookies(captured)

        # Silent re-auth on 401
        if response.status_code == 401 and not self._reauth_attempted:
            if await self._attempt_silent_reauth():
                # Retry the request once with the new cookies
                headers = self._build_headers(mutating=is_mutating, content_type=content_type)
                kwargs["headers"] = headers
                response = await request_method(target, **kwargs)
                captured = _capture_set_cookies(response)
                if captured:
                    session_store.update_cookies(captured)

        return response

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        absolute_url: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            method,
            path,
            params=params,
            json=json,
            data=data,
            files=files,
            absolute_url=absolute_url,
        )
        if not response.is_success:
            raise NoteAPIError(response.status_code, response.reason_phrase or "", response.text)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.request_json("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        json: Any | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.request_json("POST", path, json=json, data=data, files=files)

    async def put(self, path: str, *, json: Any | None = None) -> dict[str, Any]:
        return await self.request_json("PUT", path, json=json)

    async def delete(self, path: str) -> dict[str, Any]:
        return await self.request_json("DELETE", path)

    async def post_absolute(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """For uploading to S3 presigned URLs (not note.com API)."""
        if self._client is None:
            raise RuntimeError("NoteClient must be used as async context manager")
        # Don't send our cookies/XSRF to S3
        async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as s3:
            response = await s3.post(url, data=data, files=files)
        return response


def assert_authenticated() -> None:
    if not session_store.has_session():
        raise AuthError("No active note session. Run note_login first.")
