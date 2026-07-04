"""Runtime renewal boundary for expiring Vultr network permissions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from schemas.control_plane import PolicyLease
from services.vultr_events import publish_event
from services.vultr_firewall import retract_rules


_expiry_tasks: dict[str, asyncio.Task] = {}


def schedule_expiry(lease: PolicyLease) -> None:
    """Schedule automatic removal of all permissions when a lease expires."""
    existing = _expiry_tasks.pop(lease.lease_id, None)
    if existing:
        existing.cancel()
    _expiry_tasks[lease.lease_id] = asyncio.create_task(_expire(lease))


async def _expire(lease: PolicyLease) -> None:
    delay = max(0.0, (lease.expires_at - datetime.now(timezone.utc)).total_seconds())
    try:
        await asyncio.sleep(delay)
        receipt = await asyncio.to_thread(retract_rules, lease.policy)
        await publish_event(
            "policy.expired",
            lease.lease_id,
            {"lease_id": lease.lease_id, "source_doc_id": lease.source_doc_id, "receipt": receipt},
        )
    finally:
        _expiry_tasks.pop(lease.lease_id, None)


def cancel_expiry(lease_id: str) -> None:
    task = _expiry_tasks.pop(lease_id, None)
    if task:
        task.cancel()
