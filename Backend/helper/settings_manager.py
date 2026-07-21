from __future__ import annotations
from typing import Any, Dict, List
from datetime import datetime, timezone
from os import getenv
from Backend.logger import LOGGER

# ─────────────────────────────────────────────────────────────────────────────
# Default values (used when nothing exists in the DB yet)
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULTS: Dict[str, Any] = {
    "replace_mode": True,
    "hide_catalog": False,
    "auth_channels": [],
    "tmdb_api": "",
    "base_url": "",
    "upstream_repo": "",
    "upstream_branch": "",
    "admin_username": "admin",
    "admin_password": "admin",
    "subscription": False,
    "subscription_group_id": 0,
    "subscription_url": "https://t.me/",
    "approver_ids": [],
    "payment_instructions": "",
    "payment_qr_url": "",
    "http_proxy_url": "",
    "show_proxy_and_non_proxy_both": False,
    "upload_status_messages": True,
    "multi_tokens": [],
    "extra_databases": [],
    "global_search": False,
    "global_search_channels": [],
    "better_poster": "",
    "settings_revision": 0,
    "updated_at": "",
}


def get_environment_admin_credentials() -> tuple[str, str] | None:
    """
    Return an explicitly configured admin credential pair from the environment.

    ``Telegram.ADMIN_*`` has fallback values (``admin``), so it cannot tell
    whether a deployment owner actually set credentials in Hugging Face / Docker.
    This helper reads the raw environment instead.  A partial pair is ignored so
    a typo can never lock the owner out of an existing database-backed account.
    """
    username = getenv("ADMIN_USERNAME")
    password = getenv("ADMIN_PASSWORD")

    if username is None and password is None:
        return None

    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return None

    return username, password


def _has_partial_environment_admin_credentials() -> bool:
    """True when only one of the two credential environment variables is set."""
    username = getenv("ADMIN_USERNAME")
    password = getenv("ADMIN_PASSWORD")
    return (username is None) != (password is None) or (
        (username is not None or password is not None)
        and not get_environment_admin_credentials()
    )


def _explicit_environment_runtime_fallbacks() -> Dict[str, str]:
    """Return non-empty deployment values that can repair blank DB settings.

    Runtime settings normally live in MongoDB. Older deployments may already
    have an ``app_settings`` document whose TMDb key/base URL are blank, so the
    first-start environment seed never runs again. Only fill blank database
    fields; a non-empty WebUI value always remains authoritative.
    """
    tmdb_api = (getenv("TMDB_API") or "").strip()
    base_url = (getenv("BASE_URL") or "").strip().rstrip("/")

    # Hugging Face exposes the public host to Docker Spaces. This keeps bot
    # install links absolute even when BASE_URL was not entered manually.
    if not base_url:
        space_host = (getenv("SPACE_HOST") or "").strip().strip("/")
        if space_host:
            if space_host.startswith(("http://", "https://")):
                base_url = space_host.rstrip("/")
            else:
                base_url = f"https://{space_host}"

    values: Dict[str, str] = {}
    if tmdb_api:
        values["tmdb_api"] = tmdb_api
    if base_url:
        values["base_url"] = base_url
    return values


def _seed_from_env() -> Dict[str, Any]:
    """Read legacy Telegram config env values. Called only on FIRST startup."""
    from Backend.config import Telegram  # lazy import — see note at top of file

    seed = dict(_DEFAULTS)
    seed.update({
        "replace_mode":                 Telegram.REPLACE_MODE,
        "hide_catalog":                 Telegram.HIDE_CATALOG,
        "auth_channels":                list(Telegram.AUTH_CHANNEL),
        "tmdb_api":                     Telegram.TMDB_API,
        "base_url":                     Telegram.BASE_URL,
        "upstream_repo":                Telegram.UPSTREAM_REPO,
        "upstream_branch":              Telegram.UPSTREAM_BRANCH,
        "admin_username":               Telegram.ADMIN_USERNAME,
        "admin_password":               Telegram.ADMIN_PASSWORD,
        "subscription":                 Telegram.SUBSCRIPTION,
        "subscription_group_id":        Telegram.SUBSCRIPTION_GROUP_ID,
        "subscription_url":             Telegram.SUBSCRIPTION_URL,
        "approver_ids":                 list(Telegram.APPROVER_IDS),
        "global_search_channels":       [],
        "http_proxy_url":               Telegram.HTTP_PROXY_URL,
        "show_proxy_and_non_proxy_both": Telegram.SHOW_PROXY_AND_NON_PROXY_BOTH,
        "upload_status_messages":       Telegram.UPLOAD_STATUS_MESSAGES,
        "multi_tokens":                 [],
        "extra_databases":              list(Telegram.DATABASE[2:]) if len(Telegram.DATABASE) > 2 else [],
    })
    return seed


# ─────────────────────────────────────────────────────────────────────────────
# Immutable settings snapshot
# ─────────────────────────────────────────────────────────────────────────────
class Settings:
    __slots__ = ("_d",)

    def __init__(self, data: Dict[str, Any]) -> None:
        merged = dict(_DEFAULTS)
        merged.update({k: v for k, v in data.items() if k != "_id"})
        self._d = merged

    # ── Booleans ─────────────────────────────────────────────────────────────
    @property
    def replace_mode(self) -> bool:
        return bool(self._d["replace_mode"])

    @property
    def hide_catalog(self) -> bool:
        return bool(self._d["hide_catalog"])

    @property
    def subscription(self) -> bool:
        return bool(self._d["subscription"])

    @property
    def show_proxy_and_non_proxy_both(self) -> bool:
        return bool(self._d["show_proxy_and_non_proxy_both"])

    @property
    def upload_status_messages(self) -> bool:
        return bool(self._d.get("upload_status_messages", True))

    @property
    def global_search(self) -> bool:
        return bool(self._d.get("global_search", False))

    @property
    def global_search_channels(self):
        return list(self._d.get("global_search_channels") or [])

    # ── Strings ──────────────────────────────────────────────────────────────
    @property
    def tmdb_api(self) -> str:
        return str(self._d.get("tmdb_api") or "")

    @property
    def base_url(self) -> str:
        return str(self._d.get("base_url") or "").rstrip("/")

    @property
    def upstream_repo(self) -> str:
        return str(self._d.get("upstream_repo") or "")

    @property
    def upstream_branch(self) -> str:
        return str(self._d.get("upstream_branch") or "")

    @property
    def admin_username(self) -> str:
        return str(self._d.get("admin_username") or "admin")

    @property
    def admin_password(self) -> str:
        return str(self._d.get("admin_password") or "admin")

    @property
    def http_proxy_url(self) -> str:
        return str(self._d.get("http_proxy_url") or "")

    @property
    def subscription_url(self) -> str:
        return str(self._d.get("subscription_url") or "https://t.me/")

    @property
    def payment_instructions(self) -> str:
        return str(self._d.get("payment_instructions") or "")

    @property
    def payment_qr_url(self) -> str:
        return str(self._d.get("payment_qr_url") or "")

    @property
    def better_poster(self) -> str:
        return str(self._d.get("better_poster") or "").strip()

    # ── Integers ─────────────────────────────────────────────────────────────
    @property
    def subscription_group_id(self) -> int:
        return int(self._d.get("subscription_group_id") or 0)

    # ── Lists ─────────────────────────────────────────────────────────────────
    @property
    def auth_channels(self) -> List[str]:
        return list(self._d.get("auth_channels") or [])

    @property
    def approver_ids(self) -> List[int]:
        return [int(x) for x in (self._d.get("approver_ids") or [])]

    @property
    def multi_tokens(self) -> List[str]:
        return list(self._d.get("multi_tokens") or [])

    @property
    def extra_databases(self) -> List[str]:
        return list(self._d.get("extra_databases") or [])

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return dict(self._d)


# ─────────────────────────────────────────────────────────────────────────────
# Manager singleton
# ─────────────────────────────────────────────────────────────────────────────
class SettingsManager:
    _current: Settings | None = None

    # ── Bootstrap ────────────────────────────────────────────────────────────
    @classmethod
    async def initialize(cls, db) -> None:
        raw = await db.get_settings()
        if not raw:
            LOGGER.info("SettingsManager: no settings in DB — seeding from config.env.")
            seed = _seed_from_env()
            seed["settings_revision"] = 1
            seed["updated_at"] = datetime.now(timezone.utc).isoformat()
            if not await db.save_settings(seed):
                raise RuntimeError("Could not seed runtime settings into the tracking database.")
            raw = await db.get_settings()
            if not raw:
                raise RuntimeError("Runtime settings seed could not be read back from the tracking database.")
        # An explicitly supplied ADMIN_USERNAME + ADMIN_PASSWORD pair is an
        # owner-controlled recovery path.  Earlier builds only copied those
        # values on the very first launch, then an old MongoDB settings document
        # silently won forever.  That produced the "Invalid credentials" loop
        # after a code update.  Keep MongoDB in sync, but only when BOTH values
        # were deliberately supplied by the deployment owner.
        env_credentials = get_environment_admin_credentials()
        if env_credentials:
            env_username, env_password = env_credentials
            if (
                str(raw.get("admin_username") or "") != env_username
                or str(raw.get("admin_password") or "") != env_password
            ):
                updated = dict(raw)
                updated["admin_username"] = env_username
                updated["admin_password"] = env_password
                updated["settings_revision"] = int(raw.get("settings_revision") or 0) + 1
                updated["updated_at"] = datetime.now(timezone.utc).isoformat()
                if await db.save_settings(updated):
                    raw = await db.get_settings() or updated
                    LOGGER.info(
                        "SettingsManager: admin credentials synchronized from explicit environment values."
                    )
                else:
                    # Login still accepts the explicit pair directly in
                    # security.credentials, so a transient Mongo failure cannot
                    # lock the deployment owner out.
                    LOGGER.warning(
                        "SettingsManager: could not persist explicit environment admin credentials; "
                        "using them for this process anyway."
                    )
        elif _has_partial_environment_admin_credentials():
            LOGGER.warning(
                "ADMIN_USERNAME and ADMIN_PASSWORD must both be set. "
                "Keeping the existing MongoDB admin credentials unchanged."
            )

        # Repair only blank legacy fields from explicit deployment variables.
        # This addresses databases that were seeded before TMDB_API/BASE_URL
        # were configured and would otherwise keep winning on every restart.
        runtime_fallbacks = _explicit_environment_runtime_fallbacks()
        blank_repairs = {
            key: value
            for key, value in runtime_fallbacks.items()
            if not str(raw.get(key) or "").strip()
        }
        if blank_repairs:
            updated = dict(raw)
            updated.update(blank_repairs)
            updated["settings_revision"] = int(raw.get("settings_revision") or 0) + 1
            updated["updated_at"] = datetime.now(timezone.utc).isoformat()
            if await db.save_settings(updated):
                raw = await db.get_settings() or updated
                LOGGER.info(
                    "SettingsManager: repaired blank runtime setting(s) from deployment environment: %s.",
                    ", ".join(sorted(blank_repairs)),
                )
            else:
                # Keep the process usable even if Mongo has a transient write
                # failure; the next restart will retry persistence.
                raw = updated
                LOGGER.warning(
                    "SettingsManager: could not persist deployment fallbacks; "
                    "using them for this process only."
                )

        cls._current = Settings(raw)
        current = cls.current()
        LOGGER.info(
            "SettingsManager: settings loaded from tracking DB "
            "(revision=%s, tmdb_api=%s, base_url=%s).",
            current.to_dict().get("settings_revision", 0),
            "set" if current.tmdb_api else "empty",
            current.base_url or "empty",
        )

    @classmethod
    async def reload(cls, db) -> None:
        """Reload settings from DB (call after an external change)."""
        raw = await db.get_settings()
        if raw:
            cls._current = Settings(raw)

    # ── Read ─────────────────────────────────────────────────────────────────
    @classmethod
    def current(cls) -> Settings:
        if cls._current is None:
            return Settings({})
        return cls._current

    # ── Write + reinitialise ─────────────────────────────────────────────────
    @classmethod
    async def update(cls, db, new_values: Dict[str, Any]) -> Dict[str, str]:
        old = cls.current().to_dict()
        merged = dict(old)
        merged.update(new_values)

        results: Dict[str, str] = {}

        # Global Search hard requires a Userbot session — never trust the
        # client to have enforced this; guard it here too.
        if merged.get("global_search"):
            from Backend.config import Telegram
            if not Telegram.USER_SESSION_STRING:
                merged["global_search"] = False
                LOGGER.warning(
                    "SettingsManager: rejected global_search=True — "
                    "USER_SESSION_STRING is not configured."
                )
                results["global_search"] = "rejected — no Userbot session configured"

        # ── Phase 1: validate / apply things that can abort the save ───────
        old_extra = old.get("extra_databases") or []
        new_extra = merged.get("extra_databases") or []
        if old_extra != new_extra:
            result = await db.reload_extra_databases(new_extra)   # may raise ValueError
            results["databases"] = result.get("message", "databases reloaded")

        # ── Phase 2: persist, verify, then flip in-memory snapshot ─────────
        # A failed Mongo write must never look like a successful WebUI save.
        merged["settings_revision"] = int(old.get("settings_revision") or 0) + 1
        merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        if not await db.save_settings(merged):
            raise RuntimeError("MongoDB rejected the runtime-settings write. Nothing was applied.")

        persisted = await db.get_settings()
        if not persisted:
            raise RuntimeError("Runtime settings were written but could not be read back from MongoDB.")
        for key, value in new_values.items():
            if persisted.get(key) != merged.get(key):
                raise RuntimeError(f"Runtime settings verification failed for '{key}'.")

        cls._current = Settings(persisted)
        results["persistence"] = f"saved to MongoDB (revision {merged['settings_revision']})"
        LOGGER.info(
            "SettingsManager: runtime settings persisted "
            "(revision=%s, tmdb_api=%s, base_url=%s).",
            merged["settings_revision"],
            "set" if cls.current().tmdb_api else "empty",
            cls.current().base_url or "empty",
        )

        # ── Phase 3: reinit everything that reads current() ─────────────────
        results.update(await cls._reinit_dependent(old, merged))

        return results

    # ── Internal reinit logic (runs AFTER _current has been updated) ────────
    @classmethod
    async def _reinit_dependent(cls, old: dict, new: dict) -> Dict[str, str]:
        results: Dict[str, str] = {}

        # Multi-tokens changed → hot-reload Pyrogram helper clients
        old_tokens = old.get("multi_tokens") or []
        new_tokens = new.get("multi_tokens") or []
        if old_tokens != new_tokens:
            try:
                from Backend.pyrofork.clients import reload_multi_token_clients
                result = await reload_multi_token_clients()
                results["multi_tokens"] = (
                    f"{result['started']} started, {result['stopped']} stopped "
                    f"({result['total_clients']} active)"
                )
            except Exception as exc:
                LOGGER.error(f"SettingsManager reinit multi_tokens: {exc}")
                results["multi_tokens"] = f"error: {exc}"

        # Auth channels — only report when they actually changed. This was
        old_channels = old.get("auth_channels") or []
        new_channels = new.get("auth_channels") or []
        if old_channels != new_channels:
            results["auth_channels"] = f"{len(new_channels)} channel(s) saved"

        # Proxy settings changed
        proxy_keys = {"http_proxy_url", "show_proxy_and_non_proxy_both"}
        if any(old.get(k) != new.get(k) for k in proxy_keys):
            results["proxy"] = "updated — applies to next outbound request"

        # Subscription ENABLED/DISABLED toggle → actually start/stop the
        if old.get("subscription") != new.get("subscription"):
            try:
                from Backend.helper import subscription_task_manager
                from Backend.pyrofork.bot import StreamBot

                if new.get("subscription"):
                    await subscription_task_manager.start(StreamBot)
                    results["subscription"] = "checker task started"
                else:
                    await subscription_task_manager.stop()
                    results["subscription"] = "checker task stopped"
            except Exception as exc:
                LOGGER.error(f"SettingsManager reinit subscription: {exc}")
                results["subscription"] = f"error: {exc}"
        else:
            sub_keys = {"subscription_group_id", "approver_ids", "subscription_url",
                        "payment_instructions", "payment_qr_url"}
            if any(old.get(k) != new.get(k) for k in sub_keys):
                results["subscription"] = "settings reloaded in-memory"

        # Admin credentials changed
        cred_keys = {"admin_username", "admin_password"}
        if any(old.get(k) != new.get(k) for k in cred_keys):
            results["admin_credentials"] = "updated — takes effect on next login"

        # Global Search toggle changed (only meaningful logging here; the
        # search module reads SettingsManager.current() live each call)
        if old.get("global_search") != new.get("global_search") and "global_search" not in results:
            results["global_search"] = "enabled" if new.get("global_search") else "disabled"

        return results
