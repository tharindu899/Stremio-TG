"""Small safety layer for long-lived Telegram user sessions.

Pyrogram restarts sessions in a background task after a socket failure. When a
user authorization key has been revoked, that background task used to raise an
unretrieved exception and then kept producing noisy socket warnings. The app
must continue serving local streams even when optional Global Search is offline.
"""
from __future__ import annotations

from typing import Any

from Backend.logger import LOGGER

try:
    from pyrogram.errors import AuthKeyUnregistered, SessionRevoked, Unauthorized
    from pyrogram.session.session import Session
except Exception:  # pragma: no cover - only for partial dependency installs
    AuthKeyUnregistered = SessionRevoked = Unauthorized = ()
    Session = None


_SESSION_ERRORS = tuple(
    error
    for error in (Unauthorized, AuthKeyUnregistered, SessionRevoked)
    if isinstance(error, type) and issubclass(error, BaseException)
)
_PATCHED = False
_ORIGINAL_RESTART = None


def _client_name(client: Any) -> str:
    return str(
        getattr(client, "name", "")
        or getattr(client, "_name", "")
    ).strip().lower()


def is_userbot_client(client: Any) -> bool:
    return client is not None and _client_name(client) == "userbot"


def mark_userbot_session_invalid(client: Any, error: BaseException | str) -> None:
    """Disable only optional Userbot features for the current process."""
    if not is_userbot_client(client):
        return
    if getattr(client, "_tg_session_invalid", False):
        return

    setattr(client, "_tg_session_invalid", True)
    setattr(client, "_tg_session_error", str(error))
    LOGGER.error(
        "[USERBOT] Session authorization is invalid. Global Search and Userbot "
        "fallback are disabled for this run. Replace USER_SESSION_STRING and restart. (%s)",
        error,
    )


def userbot_is_usable(client: Any) -> bool:
    return is_userbot_client(client) and not bool(
        getattr(client, "_tg_session_invalid", False)
    )


def install_safe_session_restart_handler() -> None:
    """Contain invalid Userbot restart tasks so they never become unhandled.

    StreamBot errors are deliberately left unchanged because they are required
    for normal service. Only the optional user session is converted into a
    graceful feature disable.
    """
    global _PATCHED, _ORIGINAL_RESTART
    if _PATCHED or Session is None or not _SESSION_ERRORS:
        return

    original_restart = getattr(Session, "restart", None)
    if not callable(original_restart):
        return

    async def safe_restart(session, *args, **kwargs):
        try:
            return await original_restart(session, *args, **kwargs)
        except _SESSION_ERRORS as exc:
            client = getattr(session, "client", None)
            if not is_userbot_client(client):
                raise
            mark_userbot_session_invalid(client, exc)
            try:
                await session.stop()
            except Exception:
                pass
            return None

    _ORIGINAL_RESTART = original_restart
    Session.restart = safe_restart
    _PATCHED = True
