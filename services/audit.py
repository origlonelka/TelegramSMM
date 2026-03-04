"""Audit logging service."""
import json
import logging

from db.database import execute_returning

logger = logging.getLogger(__name__)


async def log_action(
    actor_user_id: int,
    action: str,
    entity_type: str = None,
    entity_id: int = None,
    details: dict | str = None,
):
    """Write an entry to audit_logs."""
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=False)
    await execute_returning(
        "INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (actor_user_id, action, entity_type, entity_id, details),
    )
