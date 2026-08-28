from functools import wraps
from flask import abort, request
from flask_login import current_user
from .extensions import db
from .models import AuditLog, ROLE_ADMIN, ROLE_MANAGER


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def can_manage_employee(employee):
    if current_user.role == ROLE_ADMIN:
        return True
    if current_user.role == ROLE_MANAGER and current_user.employee:
        return employee.manager_id == current_user.employee.id or employee.id == current_user.employee.id
    return current_user.employee and current_user.employee.id == employee.id


def log_action(action, entity, entity_id=None, details=None):
    log = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
        ip_address=client_ip(),
    )
    db.session.add(log)


def client_ip():
    """IP de auditoria após ProxyFix; evita confiar diretamente em cabeçalhos arbitrários."""
    return request.remote_addr or "unknown"
