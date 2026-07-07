from secrets import compare_digest

from fastapi import Depends, HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED
from Backend.helper.settings_manager import SettingsManager, get_environment_admin_credentials

def verify_credentials(username: str, password: str) -> bool:
    """
    Return True when a submitted pair matches the current admin credentials.

    When both ADMIN_USERNAME and ADMIN_PASSWORD are explicitly configured in
    the deployment environment, they are authoritative.  This gives the owner
    a reliable recovery path even when an older MongoDB settings document still
    contains credentials from a previous build.
    """
    configured = get_environment_admin_credentials()
    if configured:
        expected_username, expected_password = configured
    else:
        settings = SettingsManager.current()
        expected_username, expected_password = settings.admin_username, settings.admin_password

    return (
        compare_digest(str(username), str(expected_username))
        and compare_digest(str(password), str(expected_password))
    )


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
    
