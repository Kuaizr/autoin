from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from redis import Redis

from autoin.config import Settings
from autoin.infrastructure.models import LockStatePayload


@dataclass(slots=True)
class LockLease:
    key: str
    owner_id: str
    token: str
    expires_at: datetime


class LockAcquisitionError(RuntimeError):
    pass


class RedisLockManager:
    """Global UI mutex based on Redis SET NX PX semantics."""

    _RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    end
    return 0
    """

    _REFRESH_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("pexpire", KEYS[1], ARGV[2])
    end
    return 0
    """

    def __init__(self, settings: Settings, client: Redis | None = None) -> None:
        self.settings = settings
        self.client = client or Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    def acquire(self, owner_id: str) -> LockLease:
        retries = self.settings.ui_lock_retry_limit
        delay = self.settings.ui_lock_retry_delay_ms / 1000
        token = str(uuid4())

        for _ in range(retries):
            acquired = self.client.set(
                self.settings.ui_lock_key,
                token,
                nx=True,
                px=self.settings.ui_lock_ttl_ms,
            )
            if acquired:
                expires_at = datetime.now(UTC) + timedelta(milliseconds=self.settings.ui_lock_ttl_ms)
                return LockLease(
                    key=self.settings.ui_lock_key,
                    owner_id=owner_id,
                    token=token,
                    expires_at=expires_at,
                )
            time.sleep(delay)

        raise LockAcquisitionError(f"Failed to acquire UI lock after {retries} attempts.")

    def release(self, lease: LockLease) -> bool:
        result = self.client.eval(
            self._RELEASE_SCRIPT,
            1,
            lease.key,
            lease.token,
        )
        return bool(result)

    def refresh(self, lease: LockLease) -> bool:
        result = self.client.eval(
            self._REFRESH_SCRIPT,
            1,
            lease.key,
            lease.token,
            self.settings.ui_lock_ttl_ms,
        )
        if result:
            lease.expires_at = datetime.now(UTC) + timedelta(milliseconds=self.settings.ui_lock_ttl_ms)
        return bool(result)

    def snapshot(self, lease: LockLease, state: str) -> LockStatePayload:
        return LockStatePayload(
            lock_key=lease.key,
            owner_id=lease.owner_id,
            expires_at=lease.expires_at,
            state=state,
        )
