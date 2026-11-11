from .models import AuditLog


def log_audit(actor, action, entity_type, entity_id="", metadata=None, ip_address=None):
    """
    Append-only operational audit entry.
    Never call this for read-only actions.
    """
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else "",
        metadata=metadata or {},
        ip_address=ip_address,
    )