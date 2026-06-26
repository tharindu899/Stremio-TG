from fastapi import Depends, HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED
from Backend.helper.settings_manager import SettingsManager

def verify_credentials(username: str, password: str) -> bool:
    """Return True when *username* and *password* match the stored admin credentials."""
    s = SettingsManager.current()
    return username == s.admin_username and password == s.admin_password


def is_authenticated(request: Request) -> bool:
    """Return True when the session carries a valid authentication flag."""
    return bool(request.session.get("authenticated"))


def get_current_user(request: Request) -> str | None:
    """Return the logged-in username from the session, or None."""
    if is_authenticated(request):
        return request.session.get("username", "admin")
    return None


async def require_auth(request: Request) -> bool:
    """
    FastAPI dependency: raises 401 when the request is not authenticated.

    The 401 exception handler in main.py redirects the browser to /login.
    """
    if not is_authenticated(request):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return True
    
