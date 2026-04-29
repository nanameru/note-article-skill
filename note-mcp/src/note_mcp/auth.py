"""Login flow using Playwright.

Handles email+password login, then extracts cookies and the username.
On success, stores cookies in session.json and credentials in the OS keychain
so future 401s can be auto-recovered.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from note_mcp import session as session_store

logger = logging.getLogger(__name__)

NOTE_LOGIN_URL = "https://note.com/login"
NOTE_HOME_URL = "https://note.com/"
NOTE_ACCOUNT_SETTINGS_URL = "https://note.com/settings/account"

REQUIRED_COOKIE = "_note_session_v5"

DEFAULT_TIMEOUT_SEC = 600


class LoginError(RuntimeError):
    pass


def _extract_cookies(playwright_cookies: list[dict[str, Any]]) -> dict[str, str]:
    """Capture every cookie set on .note.com — don't try to filter, we don't
    know which ones note's various endpoints actually need, and they keep
    adding new ones.
    """
    out: dict[str, str] = {}
    for cookie in playwright_cookies:
        domain = (cookie.get("domain") or "").lstrip(".")
        if "note.com" not in domain:
            continue
        name = cookie.get("name", "")
        if not name:
            continue
        out[name] = cookie.get("value", "")
    if REQUIRED_COOKIE not in out:
        raise LoginError(f"Login flow finished but {REQUIRED_COOKIE} cookie was not set")
    return out


async def _read_username_via_nextjs(page: Any) -> str:
    """Read the username from Next.js's __NEXT_DATA__ blob in the page.

    Cleaner than DOM querying — note ships server-rendered props that include
    the current user. Falls back to extracting from window.__NEXT_DATA__.
    Independent technique from the deprecated DOM-scraping approach.
    """
    extracted = await page.evaluate(
        """
        () => {
            const blob = window.__NEXT_DATA__;
            if (!blob || typeof blob !== 'object') return '';
            const queue = [blob];
            const seen = new WeakSet();
            while (queue.length) {
                const cur = queue.shift();
                if (!cur || typeof cur !== 'object' || seen.has(cur)) continue;
                seen.add(cur);
                const u = cur.urlname;
                if (typeof u === 'string' && u.length > 0) return u;
                for (const k of Object.keys(cur)) {
                    const v = cur[k];
                    if (v && typeof v === 'object') queue.push(v);
                }
            }
            return '';
        }
        """
    )
    return extracted or ""


async def login_with_browser(
    *,
    email: str | None = None,
    password: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    headless: bool = False,
) -> dict[str, Any]:
    """Open a browser, perform login, persist cookies + credentials.

    Args:
        email/password: If provided, perform automatic login. If omitted, the
            user logs in manually in the visible browser window.
        timeout: Manual-login wait time in seconds.
        headless: Run headless. Useful for silent re-auth from saved creds.

    Returns:
        dict with {"username", "user_id", "cookies"}.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        # If we already have cookies, prime the context to skip login
        existing = (session_store.load_session() or {}).get("cookies") or {}
        if existing:
            await context.add_cookies(
                [
                    {
                        "name": k,
                        "value": v,
                        "domain": ".note.com",
                        "path": "/",
                    }
                    for k, v in existing.items()
                    if v
                ]
            )

        await page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded")

        def is_logged_in(url: str) -> bool:
            if not url.startswith(NOTE_HOME_URL):
                return False
            return not any(seg in url for seg in ("/login", "/signup", "/auth", "/oauth"))

        if is_logged_in(page.url):
            logger.info("Already authenticated via existing cookies")
        elif email and password:
            logger.info("Performing automatic login")
            await page.locator('input[name="email"]').fill(email)
            await page.locator('input[name="password"]').fill(password)
            await page.locator('button[type="submit"]').click()
            try:
                await page.wait_for_url(is_logged_in, timeout=30_000)
            except Exception as exc:
                raise LoginError(f"Automatic login did not redirect to home: {exc}") from exc
        else:
            logger.info("Waiting for manual login (timeout=%ss)", timeout)
            try:
                await page.wait_for_url(is_logged_in, timeout=timeout * 1000)
            except Exception as exc:
                raise LoginError(f"Manual login timed out after {timeout}s") from exc

        # Hit account settings to ensure XSRF + auth cookies are all present
        await page.goto(NOTE_ACCOUNT_SETTINGS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(1)

        # Try Next.js data first (cleanest), fallback to API after we have cookies
        username = await _read_username_via_nextjs(page)
        cookies_raw = await context.cookies()
        cookies = _extract_cookies(cookies_raw)

        await browser.close()

    # Persist cookies first so the API client can use them
    saved = session_store.load_session() or {}
    saved.update(
        {
            "cookies": {**(saved.get("cookies") or {}), **cookies},
            "username": username or saved.get("username", ""),
            "user_id": saved.get("user_id", ""),
        }
    )
    session_store.save_session(saved)

    # If __NEXT_DATA__ extraction failed, fall back to API lookup. This is
    # the most reliable path — note's API will tell us authoritatively who
    # the current user is.
    if not username:
        try:
            from note_mcp.whoami import refresh_username_in_session

            username = await refresh_username_in_session()
            saved = session_store.load_session() or {}
        except Exception as exc:
            logger.warning("API-based username lookup failed: %s", exc)

    if email and password:
        try:
            session_store.save_credentials(email, password)
        except Exception as exc:  # keychain may be locked
            logger.warning("Could not save credentials to keychain: %s", exc)

    return {
        "username": username,
        "user_id": saved.get("user_id", ""),
        "cookies_saved": list(cookies.keys()),
        "cookie_count": len(cookies),
    }
