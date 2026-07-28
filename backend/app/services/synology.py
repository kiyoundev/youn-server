import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

_log = logging.getLogger(__name__)

_BAY_COUNT = 2  # DS216+
_DSM_SESSION_NAME = "webui"
_DSM_SESSION_INVALID_CODES = {106, 119}  # 106 = session timeout, 119 = invalid session

_DISK_STATUS_MAP = {
    "normal": "healthy",
    "initialized": "healthy",
    "crashed": "error",
    "system_partition_failed": "error",
    "not_initialized": "warning",
    "uninitialized": "warning",
}


def _disk_status(raw: str) -> str:
    return _DISK_STATUS_MAP.get(raw, "warning")


def _bytes_to_tb(n: float) -> float:
    return n / 1_000_000_000_000


@dataclass
class BayState:
    label: str
    status: str  # "empty" | "healthy" | "warning" | "error"


@dataclass
class StorageState:
    bays: list[BayState]
    available: float  # TB
    used: float  # TB
    reserved: float  # TB


class _SessionExpired(Exception):
    """Raised internally when DSM reports the cached sid is no longer valid."""


class SynologyClient:
    def __init__(self) -> None:
        self._sid: str | None = None
        self._lock = asyncio.Lock()

    @property
    def _enabled(self) -> bool:
        return bool(
            settings.synology_host and settings.synology_user and settings.synology_password
        )

    @property
    def _base_url(self) -> str:
        scheme = "https" if settings.synology_use_https else "http"
        return f"{scheme}://{settings.synology_host}:{settings.synology_port}"

    async def get_storage(self) -> StorageState | None:
        if not self._enabled:
            _log.warning("Synology credentials not set — SynologyClient disabled")
            return None

        async with httpx.AsyncClient(timeout=10, verify=settings.synology_verify_ssl) as client:
            sid = await self._get_sid(client)
            if not sid:
                return None
            try:
                return await self._fetch_storage(client, sid)
            except _SessionExpired:
                sid = await self._get_sid(client, force_refresh=True)
                if not sid:
                    return None
                try:
                    return await self._fetch_storage(client, sid)
                except _SessionExpired:
                    _log.warning("Synology session invalid immediately after re-login")
                    return None

    async def _get_sid(
        self, client: httpx.AsyncClient, force_refresh: bool = False
    ) -> str | None:
        async with self._lock:
            if self._sid and not force_refresh:
                return self._sid
            self._sid = await self._login(client)
            return self._sid

    async def _login(self, client: httpx.AsyncClient) -> str | None:
        try:
            resp = await client.get(
                f"{self._base_url}/webapi/auth.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "version": 6,
                    "method": "login",
                    "account": settings.synology_user,
                    "passwd": settings.synology_password,
                    "session": _DSM_SESSION_NAME,
                    "format": "sid",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                _log.warning("Synology login failed: %s", data.get("error"))
                return None
            return data["data"]["sid"]
        except Exception:
            _log.warning("Synology login request failed", exc_info=True)
            return None

    async def _logout(self, client: httpx.AsyncClient, sid: str) -> None:
        try:
            await client.get(
                f"{self._base_url}/webapi/auth.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "version": 6,
                    "method": "logout",
                    "session": _DSM_SESSION_NAME,
                    "_sid": sid,
                },
            )
        except Exception:
            _log.warning("Synology logout failed", exc_info=True)

    async def close(self) -> None:
        """Log out the cached DSM session, if one is held. Call on app shutdown."""
        async with self._lock:
            if not self._sid:
                return
            async with httpx.AsyncClient(timeout=10, verify=settings.synology_verify_ssl) as client:
                await self._logout(client, self._sid)
                self._sid = None

    async def _fetch_storage(self, client: httpx.AsyncClient, sid: str) -> StorageState | None:
        try:
            resp = await client.get(
                f"{self._base_url}/webapi/entry.cgi",
                params={
                    "api": "SYNO.Storage.CGI.Storage",
                    "version": 1,
                    "method": "load_info",
                    "_sid": sid,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                error_code = (data.get("error") or {}).get("code")
                if error_code in _DSM_SESSION_INVALID_CODES:
                    raise _SessionExpired
                _log.warning("Synology storage query failed: %s", data.get("error"))
                return None
            return self._parse_storage(data["data"])
        except _SessionExpired:
            raise
        except Exception:
            _log.warning("Synology storage query request failed", exc_info=True)
            return None

    def _parse_storage(self, data: dict) -> StorageState:
        disks_by_slot = {disk.get("slot_id"): disk for disk in data.get("disks", [])}
        bays = [
            BayState(
                label=str(slot),
                status=_disk_status(disks_by_slot[slot].get("status", ""))
                if slot in disks_by_slot
                else "empty",
            )
            for slot in range(1, _BAY_COUNT + 1)
        ]

        volumes = data.get("volumes", [])
        volume_total = sum(int(v["size"]["total"]) for v in volumes if v.get("size"))
        volume_used = sum(int(v["size"]["used"]) for v in volumes if v.get("size"))
        volume_free = max(0, volume_total - volume_used)

        pools = data.get("storagePools") or []
        pool_total = sum(int(p["size"]["total"]) for p in pools if p.get("size")) or volume_total
        reserved_bytes = max(0, pool_total - volume_total)

        return StorageState(
            bays=bays,
            available=_bytes_to_tb(volume_free),
            used=_bytes_to_tb(volume_used),
            reserved=_bytes_to_tb(reserved_bytes),
        )


synology_client = SynologyClient()
