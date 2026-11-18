"""Audit trail. Kept free of other module imports so any router can call it."""

import json

from sqlalchemy.orm import Session

from app.modules.admin.models import AuditLog
from app.modules.auth.models import User


def record(
    db: Session,
    admin: User,
    action: str,
    target_type: str,
    target_id: int | None = None,
    label: str = "",
    details: dict | None = None,
) -> None:
    """Write one audit row (call after the action succeeded)."""
    db.add(
        AuditLog(
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=label[:200],
            details=json.dumps(details or {}, ensure_ascii=False),
        )
    )
    db.commit()
