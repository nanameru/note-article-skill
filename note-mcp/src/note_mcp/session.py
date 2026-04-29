"""Session storage for note-mcp.

Cookies live in ~/.note-mcp/session.json (mode 0600). Credentials
(email/password) are stored in the OS keychain so silent re-login is possible
when cookies expire.

Why file storage for cookies and not keychain:
- note.com's `_note_session_v5` cookie rotates on every request. We need to
  persist it back after every API call. Keychain writes are slow and can
  prompt the user on locked keychains, which would break the self-healing
  flow. Plain file is correct here — and we still keep mode 0600.

The keychain still holds the password, which is the actually sensitive
credential.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import keyring

SERVICE_NAME = "note-mcp"
KEYCHAIN_USERNAME_KEY = "_email"
KEYCHAIN_PASSWORD_KEY = "_password"

DEFAULT_DIR = Path.home() / ".note-mcp"
SESSION_FILE = DEFAULT_DIR / "session.json"


def _ensure_dir() -> None:
    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DEFAULT_DIR, 0o700)
    except OSError:
        pass


def _write_secure(path: Path, content: str) -> None:
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    tmp.replace(path)


def load_session() -> dict[str, Any] | None:
    """Load session JSON. Returns None if no session yet."""
    if not SESSION_FILE.exists():
        return None
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_session(data: dict[str, Any]) -> None:
    """Persist the full session dict atomically with mode 0600."""
    _write_secure(SESSION_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def clear_session() -> None:
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except OSError:
            pass


def update_cookies(new_cookies: dict[str, str]) -> None:
    """Merge cookies into the saved session. Used after every API call."""
    data = load_session() or {"cookies": {}, "username": "", "user_id": ""}
    cookies = data.get("cookies") or {}
    cookies.update({k: v for k, v in new_cookies.items() if v is not None})
    data["cookies"] = cookies
    save_session(data)


def save_credentials(email: str, password: str) -> None:
    """Store login credentials in the OS keychain for silent re-login."""
    keyring.set_password(SERVICE_NAME, KEYCHAIN_USERNAME_KEY, email)
    keyring.set_password(SERVICE_NAME, KEYCHAIN_PASSWORD_KEY, password)


def load_credentials() -> tuple[str, str] | None:
    email = keyring.get_password(SERVICE_NAME, KEYCHAIN_USERNAME_KEY)
    password = keyring.get_password(SERVICE_NAME, KEYCHAIN_PASSWORD_KEY)
    if email and password:
        return email, password
    return None


def clear_credentials() -> None:
    for key in (KEYCHAIN_USERNAME_KEY, KEYCHAIN_PASSWORD_KEY):
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass
        except Exception:
            pass


def has_session() -> bool:
    data = load_session()
    if not data:
        return False
    cookies = data.get("cookies") or {}
    return bool(cookies.get("_note_session_v5"))
